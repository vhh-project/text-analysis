#!/usr/bin/env python
# coding: utf-8

import matplotlib.pyplot as plt


def plot_img(img, dpi=80):
    '''
    img - already loaded from PIL
    '''
    plt.figure(num=None, figsize=(10, 10), dpi=dpi, facecolor='y', edgecolor='k')
    plt.imshow(img, cmap='Greys_r')
