#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
# pylint: disable=E1137,E1136,E0110
import sys
import os
import time
import collections

import argparse

import numpy as np

import rasterio

import keras.backend as K
import keras.callbacks
import keras.utils
from keras.optimizers import SGD, Adam, RMSprop, Adadelta
from keras.models import Model
from keras.layers import Input, Dense, Activation, MaxPooling2D, Conv2D, BatchNormalization
from keras.layers import Concatenate, Cropping2D, Lambda
from keras.losses import categorical_crossentropy, mean_squared_error

from keras.preprocessing.image import ImageDataGenerator

from sklearn.cluster import MiniBatchKMeans

import scipy.spatial.distance

def manual_kmeans_predict(x_all, cluster_centers, step_size=100000):
    ''' Faster inference of cluster membership than default sklearn model.predict().
    If you have fit a sklearn.cluster algorithm (like KMeans or MiniBatchKMeans) on a subset of your data
    (or fit with `compute_labels=False`), then you can use this method to more quickly predict the cluster
    memberships than calling `.predict()`.
    Example:
    ```
    kmeans = MiniBatchKMeans(n_clusters=9, compute_labels=False)
    kmeans.fit(x_all[::100,])
    labels = utils.manual_kmeans_predict(x_all, kmeans.cluster_centers_)
    ```
    '''
    print("Manual predict")
    y_all = np.zeros((x_all.shape[0]), dtype=np.uint8)
    for i in range(0, x_all.shape[0], step_size):
        if (i // step_size) % 50 == 0:
            print(i // step_size, x_all.shape[0]//step_size)
        l = scipy.spatial.distance.cdist(x_all[i:i+step_size], cluster_centers).argmin(axis=1)
        y_all[i:i+step_size] = l
    return y_all


def image_cutout_augmentation(image, mask_size=(5,20)):
    height, width, _ = image.shape
    
    if isinstance(mask_size, tuple):
        size = np.random.randint(*mask_size)
    elif isinstance(mask_size, int):
        size = mask_size
    else:
        raise ValueError("mask_size must be int or tuple")

    x = np.random.randint(0, width-size)
    y = np.random.randint(0, height-size)
    
    image[y:y+size, x:x+size] = 0
    return image


def basic_model(input_shape, num_classes, lr=0.003):
    inputs = Input(input_shape)

    x1 = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(inputs)
    x2 = Conv2D(128, kernel_size=(5,5), strides=(1,1), padding="same", activation="relu")(inputs)
    x3 = Conv2D(128, kernel_size=(7,7), strides=(1,1), padding="same", activation="relu")(inputs)
    x = Concatenate(axis=-1)([x1,x2,x3])
    x = Conv2D(128, kernel_size=(1,1), strides=(1,1), padding="same", activation="relu")(x)

    x1 = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(x)
    x2 = Conv2D(128, kernel_size=(5,5), strides=(1,1), padding="same", activation="relu")(x)
    x3 = Conv2D(128, kernel_size=(7,7), strides=(1,1), padding="same", activation="relu")(x)
    x = Concatenate(axis=-1)([x1,x2,x3])
    x = Conv2D(128, kernel_size=(1,1), strides=(1,1), padding="same", activation="relu")(x)

    x1 = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(x)
    x2 = Conv2D(128, kernel_size=(5,5), strides=(1,1), padding="same", activation="relu")(x)
    x3 = Conv2D(128, kernel_size=(7,7), strides=(1,1), padding="same", activation="relu")(x)
    x = Concatenate(axis=-1)([x1,x2,x3])
    x = Conv2D(128, kernel_size=(1,1), strides=(1,1), padding="same", activation="relu")(x)

    x1 = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(x)
    x2 = Conv2D(128, kernel_size=(5,5), strides=(1,1), padding="same", activation="relu")(x)
    x3 = Conv2D(128, kernel_size=(7,7), strides=(1,1), padding="same", activation="relu")(x)
    x = Concatenate(axis=-1)([x1,x2,x3])
    x = Conv2D(128, kernel_size=(1,1), strides=(1,1), padding="same", activation="relu")(x)

    outputs = Conv2D(num_classes, kernel_size=(1,1), strides=(1,1), padding="same", activation="softmax")(x)
    model = Model(inputs=inputs, outputs=outputs)
    
    optimizer = Adam(lr=lr)
    model.compile(loss=categorical_crossentropy, optimizer=optimizer)
    
    return model


# def basic_model(input_shape, num_classes, lr=0.003):
#     inputs = Input(input_shape)

#     x = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(inputs)
#     x = BatchNormalization()(x)
#     x = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(x)
#     x = BatchNormalization()(x)
#     x = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(x)
#     x = BatchNormalization()(x)
#     x = Conv2D(128, kernel_size=(3,3), strides=(1,1), padding="same", activation="relu")(x)
#     x = BatchNormalization()(x)

#     x = Conv2D(128, kernel_size=(1,1), strides=(1,1), padding="same", activation="relu")(x)

#     outputs = Conv2D(num_classes, kernel_size=(1,1), strides=(1,1), padding="same", activation="softmax")(x)
#     model = Model(inputs=inputs, outputs=outputs)
    
#     optimizer = Adam(lr=lr)
#     model.compile(loss=categorical_crossentropy, optimizer=optimizer)
    
#     return model


def main():
    parser = argparse.ArgumentParser(description="Autoencoder training")

    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debugging", default=False)
    parser.add_argument("--input_fn", action="store", dest="input_fn", type=str, help="Path to input GeoTIFF", required=True)
    parser.add_argument("--output_fn", action="store", dest="output_fn", type=str, help="Output model fn format", required=True)
    parser.add_argument("--gpu", action="store", dest="gpuid", type=int, help="GPU to use", required=True)

    args = parser.parse_args(sys.argv[1:])
    args.batch_size = 10
    args.num_epochs = 30

    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpuid)
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 

    start_time = float(time.time())
    
    
    print("Loading data")
    f = rasterio.open(args.input_fn,"r")
    data = np.rollaxis(f.read(), 0, 3)
    f.close()

    # data = np.concatenate([
    #     data,
    #     data[:,:,0][:,:,np.newaxis]
    # ], axis=2)

    # assert data.shape[2] == 4
    print("Loaded data with shape:", data.shape)

    print("Fitting KMeans model for labels")
    num_classes = 64
    data_original_shape = data.shape
    data_color_features = data.reshape(-1,data_original_shape[2])
    mask = (data_color_features == 0).sum(axis=1) != data_original_shape[2]
    kmeans = MiniBatchKMeans(n_clusters=num_classes, verbose=1, init_size=2**16, n_init=20, batch_size=2**14, compute_labels=False)
    kmeans = kmeans.fit(data_color_features[mask])
    #labels = kmeans.fit_predict(data_color_features)
    labels = manual_kmeans_predict(data_color_features, cluster_centers=kmeans.cluster_centers_)
    data_color_labels = labels.reshape(data_original_shape[:2])

    print("Extracting training samples")
    n_samples = 5000
    height, width = 150, 150
    x_all = np.zeros((n_samples, height, width, data_original_shape[2]), dtype=np.float32)
    y_all = np.zeros((n_samples, height, width), dtype=np.float32)

    for i in range(n_samples):
        x = np.random.randint(0, data.shape[1]-width)
        y = np.random.randint(0, data.shape[0]-height)
        
        while np.any((data[y:y+height, x:x+width, :] == 0).sum(axis=2) == data_original_shape[2]):
            x = np.random.randint(0, data.shape[1]-width)
            y = np.random.randint(0, data.shape[0]-height)
        
        img = data[y:y+height, x:x+width, :].astype(np.float32)
        target = data_color_labels[y:y+height, x:x+width].copy()
        
        x_all[i] = img
        y_all[i] = target

    del data, data_color_labels, data_color_features
    x_all = x_all/255.0
    y_all = keras.utils.to_categorical(y_all, num_classes=num_classes)


    model = basic_model((height, width, data_original_shape[2]), num_classes, lr=0.003)
    model.summary()

    print("Fitting model")

    datagen = ImageDataGenerator(
        rotation_range=0,
        width_shift_range=0,
        height_shift_range=0,
        channel_shift_range=0.1,
        fill_mode='constant', # can also be "nearest"
        cval=0.0,
        horizontal_flip=False,
        vertical_flip=False,
        preprocessing_function=image_cutout_augmentation,
        dtype=np.float32
    )


    model_checkpoint = keras.callbacks.ModelCheckpoint(args.output_fn, monitor='train_loss', verbose=1, save_best_only=False, save_weights_only=False, mode='auto', period=1)
    #model.fit(x_all, y_all, batch_size=32, epochs=30, verbose=1, callbacks=[model_checkpoint], validation_split=0.1)

    model.fit_generator(
        datagen.flow(x_all, y_all, batch_size=args.batch_size),
        steps_per_epoch=x_all.shape[0] / args.batch_size,
        epochs=args.num_epochs,
        callbacks=[model_checkpoint],
        validation_data=datagen.flow(x_all, y_all, batch_size=args.batch_size),
        validation_steps=50
    )



    print("Finished in %0.4f seconds" % (time.time() - start_time))

if __name__ == "__main__":
    main()
