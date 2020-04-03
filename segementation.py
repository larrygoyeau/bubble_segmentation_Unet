# -*- coding: utf-8 -*-
"""segementation.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1k1fKiAqa9jJFbO_in36y4-1Ke-taTA5D
"""

import logging
logging.getLogger('tensorflow').disabled = True

# Install required libs
import os
os.system('pip install -U git+https://github.com/albu/albumentations')
os.system('pip install -U efficientnet')
os.system('pip install image-classifiers==1.0.0b1')
os.system('git clone https://github.com/qubvel/segmentation_models')

import random
from PIL import Image
from io import BytesIO
from google.colab import files
import cv2
import keras
import numpy as np
import matplotlib.pyplot as plt
import albumentations as A
import segmentation_models as sm

# helper function for data visualization
def visualize(**images):
    """PLot images in one row."""
    n = len(images)
    plt.figure(figsize=(16, 10))
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
        shape_image=image.shape
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
            
        return image, shape_image
        
    def __len__(self):
        return len(self.ids_image)

def round_clip_0_1(x, **kwargs):
    return x.round().clip(0, 1)


def get_validation_augmentation(I,J):
    """Add paddings to make image shape divisible by 32"""
    test_transform = [A.PadIfNeeded(384, 544, border_mode=0)]
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

# define optimizer
optim = keras.optimizers.Adam(LR)

from keras.models import model_from_json

json_file = open('/content/bubble_segmentation/best_model.json', 'r')
loaded_model_json = json_file.read()
json_file.close()
model = model_from_json(loaded_model_json)

# load weights into new model, you can change the path if you don't use colab
model.load_weights("/content/bubble_segmentation/best_model.h5")
print("Loaded model from disk")

# compile keras model with defined optimozer, loss and metrics
model.compile(optim,loss='categorical_crossentropy')

import sys
sys.setrecursionlimit(100000)

def color_bubble(mask,i,j,I,J,random_color,color):
  if all(mask[i,j]==color) and (i,j)!=(0,0):
    if i==I-1 or j==J-1 or i==0 or j==0:
      mask[0,0][1]=mask[0,0][1]+1 #number of pixel in contacte with the border
    mask[0,0][0]=mask[0,0][0]+1   #size bubble
    mask[i,j]=random_color
    if 0<j:
      color_bubble(mask,i,j-1,I,J,random_color,color)
    if i<I-1:
      color_bubble(mask,i+1,j,I,J,random_color,color)
    if 0<i:
      color_bubble(mask,i-1,j,I,J,random_color,color)
    if j<J-1:
      color_bubble(mask,i,j+1,I,J,random_color,color)
    
def uncolor_bubble(mask,i,j,I,J,color_liquide,random_color):
  if all(mask[i,j]==random_color):
    mask[i,j]=color_liquide
    if 0<j:
      uncolor_bubble(mask,i,j-1,I,J,color_liquide,random_color)
    if i<I-1:
      uncolor_bubble(mask,i+1,j,I,J,color_liquide,random_color)
    if 0<i:
      uncolor_bubble(mask,i-1,j,I,J,color_liquide,random_color)
    if j<J-1:
      uncolor_bubble(mask,i,j+1,I,J,color_liquide,random_color)
    
# The fonuction bellow select a good color for bubble

def the_color(random_color,threshold):
  if random_color[0]-random_color[1]<threshold and random_color[0]-random_color[2]<threshold:
    random_color=[random.randint(4, 255),random.randint(4, 255),random.randint(4, 255)]
    return(the_color(random_color,threshold))
  else:
    return(random_color)
    
# The fonuction bellow will color each bubbles and return the size of each bubbles

def foam(mask,color_air,threshold,color_liquide,image_name,remove_bubbles_on_the_border):
  file = open(image_name[:-4]+".txt","w")
  file.write("Bubble index and its size\n")
  I=len(mask)
  J=len(mask[0])
  bubble=0
  size_of_bubbles=[]
  for i in range(I):
    for j in range(J):
      if all(mask[i,j]==color_air):
        mask[0,0][0]=0 #size of bubbles
        mask[0,0][1]=0 #number of pixel in contacte with the border
        random_color=[random.randint(4, 255),random.randint(4, 255),random.randint(4, 255)]
        random_color=the_color(random_color,60)
        color_bubble(mask,i,j,I,J,random_color,color_air)
        size_bubble=int(mask[0,0][0])
        if len(size_of_bubbles)>3 and size_bubble<threshold*sum(size_of_bubbles)/len(size_of_bubbles):
          uncolor_bubble(mask,i,j,I,J,color_liquide,random_color)
        elif mask[0,0][1]>0 and remove_bubbles_on_the_border:
          uncolor_bubble(mask,i,j,I,J,color_liquide,random_color)
        else:
          bubble=bubble+1
          size_of_bubbles=size_of_bubbles+[size_bubble]
          file.write(str(bubble)+"  "+str(size_bubble)+"\n")
  file.close() 
  print("Number of detected bubbles "+str(bubble))
  return(size_of_bubbles)

def segment_image(uploaded,remove_bubbles_on_the_border):
  
  size_of_bubbles=[]
  
  for image_uploaded in uploaded:
    print('\n')
    image=Image.open(BytesIO(uploaded[image_uploaded]))
    image = np.asarray(image)

    test_dataset = Dataset(
      image=image,
      preprocessing=get_preprocessing(preprocess_input),
      augmentation=get_validation_augmentation
    )

    image, shape_image= test_dataset[0]
    image = np.expand_dims(image, axis=0)
    pr_mask = model.predict(image).round()[0]
    
    image=image[0]
    image=image[int((len(image)-shape_image[0])/2):int((len(image)-shape_image[0])/2)+shape_image[0]]
    image=image[:,int((len(image[0])-shape_image[1])/2):int((len(image[0])-shape_image[1])/2)+shape_image[1]]
    pr_mask=pr_mask[int((len(pr_mask)-shape_image[0])/2):int((len(pr_mask)-shape_image[0])/2)+shape_image[0]]
    pr_mask=pr_mask[:,int((len(pr_mask[0])-shape_image[1])/2):int((len(pr_mask[0])-shape_image[1])/2)+shape_image[1]]
    
    size_of_bubbles=size_of_bubbles+foam(pr_mask[:,:-1], color_air=[1,0,0],threshold=0.015,color_liquide=[0,1,0], image_name=image_uploaded, remove_bubbles_on_the_border=remove_bubbles_on_the_border)
    
    image=denormalize(image.squeeze())
    I=len(image)
    J=len(image[0])
    mask_plus_image=pr_mask.copy()
    mask=pr_mask.copy()
    for i in range(I):
      for j in range(J):
        if pr_mask[i,j][2]==1.0 or pr_mask[i,j][1]==1.0 or all(pr_mask[i,j]==0):
          mask_plus_image[i,j]=image[i,j]*255
          mask[i,j]=0
    
    visualize(mask_plus_image=denormalize(mask_plus_image.squeeze()))
    cv2.imwrite('mask_plus_'+image_uploaded, mask_plus_image)
    cv2.imwrite('mask_of_'+image_uploaded, mask)
  return(size_of_bubbles)
