# -*- coding: utf-8 -*-
"""segementation.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1k1fKiAqa9jJFbO_in36y4-1Ke-taTA5D
"""

# Install required libs

!pip install -U git+https://github.com/albu/albumentations
!git clone https://github.com/qubvel/segmentation_models
!pip install -U efficientnet
!pip install image-classifiers==1.0.0b1

from PIL import Image
from io import BytesIO
from google.colab import files
import segmentation_models as sm
import os
import cv2
import keras
import numpy as np
import matplotlib.pyplot as plt
import albumentations as A

# helper function for data visualization
def visualize(**images):
    """PLot images in one row."""
    n = len(images)
    plt.figure(figsize=(16, 5))
    for i, (name, image) in enumerate(images.items()):
        plt.subplot(1, n, i + 1)
        plt.xticks([])
        plt.yticks([])
        plt.title(' '.join(name.split('_')).title())
        plt.imshow(image)
    plt.show()
    
# helper function for data visualization    
def denormalize(x):
    """Scale image to range 0..1 for correct plot"""
    x_max = np.percentile(x, 98)
    x_min = np.percentile(x, 2)    
    x = (x - x_min) / (x_max - x_min)
    x = x.clip(0, 1)
    return x
    

# classes for data loading and preprocessing
class Dataset:
    
    def __init__(
            self, 
            image=None,
            images_dir=None,
            preprocessing=None,
            augmentation=None,
    ):
        self.ids_image = os.listdir(images_dir)
        
        if images_dir!=None:
          self.images_fps = [os.path.join(images_dir, image_id) for image_id in self.ids_image]
        else:
          self.images_fps=None
   
        self.preprocessing = preprocessing

        self.augmentation=augmentation

        self.image=image
    
    def __getitem__(self, i):
        
        # read data
        if self.images_fps!=None:
          image = cv2.imread(self.images_fps[i])
        else:
          image = self.image
        p=255/(image.max()-image.min())
        image=(image-image.min())*p
        image= image.astype(np.uint8)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        if self.augmentation:
          I=len(image)
          J=len(image[0])
          sample = self.augmentation(I,J)(image=image)
          image = sample['image']
        
        # apply preprocessing
        if self.preprocessing:
            sample = self.preprocessing(image=image)
            image= sample['image']
            
        return image
        
    def __len__(self):
        return len(self.ids_image)

def round_clip_0_1(x, **kwargs):
    return x.round().clip(0, 1)

def get_validation_augmentation(I,J):
    """Add paddings to make image shape divisible by 32"""
    test_transform = [A.PadIfNeeded(384, 544, border_mode=0)]
    if 256<I and 512<J:
      test_transform = [A.PadIfNeeded(384, 544, border_mode=0)]
    elif np.log(I)/np.log(2)%1==0 and np.log(J)/np.log(2)%1==0:
      test_transform = [A.PadIfNeeded(I, J, border_mode=0)]
    elif np.log(I)/np.log(2)%1==0:
      test_transform = [A.PadIfNeeded(I, 2**(int(np.log(J)/np.log(2))+1), border_mode=0)]
    elif np.log(J)/np.log(2)%1==0:
      test_transform = [A.PadIfNeeded( 2**(int(np.log(I)/np.log(2))+1), J, border_mode=0)]
    else:
      test_transform = [A.PadIfNeeded(2**(int(np.log(I)/np.log(2))+1), 2**(int(np.log(J)/np.log(2))+1), border_mode=0)]
    return A.Compose(test_transform)

def get_preprocessing(preprocessing_fn):
    """Construct preprocessing transform
    
    Args:
        preprocessing_fn (callbale): data normalization function 
            (can be specific for each pretrained neural network)
    Return:
        transform: albumentations.Compose
    
    """
    
    _transform = [
        A.Lambda(image=preprocessing_fn),
    ]
    return A.Compose(_transform)

BACKBONE = 'efficientnetb3'
preprocess_input = sm.get_preprocessing(BACKBONE)
LR = 0.0001

# define network parameters
n_classes =3 # case for binary and multiclass segmentation
activation = 'softmax'

#create model
model = sm.Unet(BACKBONE, classes=n_classes, activation=activation)

# define optimizer
optim = keras.optimizers.Adam(LR)

# Segmentation models losses can be combined together by '+' and scaled by integer or float factor
dice_loss = sm.losses.DiceLoss()
focal_loss = sm.losses.CategoricalFocalLoss()
total_loss = dice_loss + (1 * focal_loss)

# load weights into new model, you can change the path if you don't use colab
model.load_weights("/content/bubble_segmentation/best_model.h5")
print("Loaded model from disk")

# compile keras model with defined optimozer, loss and metrics
model.compile(optim, total_loss)

import sys
sys.setrecursionlimit(100000)

def color_bubble(mask,i,j,I,J,bubble,color):
  if all(mask[i,j]==color) and (i,j)!=(0,0):
    mask[0,0][0]=mask[0,0][0]+1   #size bubble
    mask[i,j]=[bubble%253+2, bubble%85+20, bubble%170+2]
    if 0<j:
      color_bubble(mask,i,j-1,I,J,bubble,color)
    if i<I-1:
      color_bubble(mask,i+1,j,I,J,bubble,color)
    if 0<i:
      color_bubble(mask,i-1,j,I,J,bubble,color)
    if j<J-1:
      color_bubble(mask,i,j+1,I,J,bubble,color)
    
def uncolor_bubble(mask,i,j,I,J,color_liquide,color):
  if all(mask[i,j]==[color%253+2, color%85+20, color%170+2]):
    mask[i,j]=color_liquide
    if 0<j:
      uncolor_bubble(mask,i,j-1,I,J,color_liquide,color)
    if i<I-1:
      uncolor_bubble(mask,i+1,j,I,J,color_liquide,color)
    if 0<i:
      uncolor_bubble(mask,i-1,j,I,J,color_liquide,color)
    if j<J-1:
      uncolor_bubble(mask,i,j+1,I,J,color_liquide,color)
    
# The fonuction bellow will color each bubbles

def foam(mask,color_air,threshold,color_liquide):
  I=len(mask)
  J=len(mask[0])
  bubble=0
  n=0
  for i in range(I):
    for j in range(J):
      if all(mask[i,j]==color_air):
        mask[0,0][0]=0
        color_bubble(mask,i,j,I,J,bubble,color_air)
        size_bubble=mask[0,0][0]
        if size_bubble<threshold:
          uncolor_bubble(mask,i,j,I,J,color_liquide,bubble)
        else:
          bubble=bubble+40
          n=n+1
  print("Number of detected bubbles "+str(n))