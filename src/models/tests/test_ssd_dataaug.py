import tensorflow as tf
import numpy as np
import cv2
import json
import random

# Regresar un directoria para poder acceder modulo de otra carpeta
import sys
sys.path.append("..")
from ops.SSD import iou_batch, intersection_over_union, ssd_sample_patch
from ops.SSD import ssd_expand_image
sys.path.append("tests/")

from test_bboxes import draw_bbox

def main():
    path_to_image = "test_images/000000000670.jpg"
    path_to_ann = "test_images/000000000670.jpg.json"

    with open(path_to_ann) as json_text:
        ann = json.loads(json_text.read())

    image = cv2.imread(path_to_image)
    bboxes_numpy = np.ones((len(ann["bboxes"]), 4))
    cats = []
    for i in range(len(ann["bboxes"])):
        bbox = ann["bboxes"][i]
        x = bbox["center_x"]
        y = bbox["center_y"]
        w = bbox["width"]
        h = bbox["height"]
        bboxes_numpy[i, :] = [x, y, w, h]
        cats.append(bbox["category_id"])
        #bboxes_tensor[i, 0] = x
        #draw_bbox(img=image, bbox=(x, y, w, h))

    aug_image, aug_bboxes = ssd_expand_image(image, bboxes_numpy)
    aug_image, aug_bboxes, aug_cats = ssd_sample_patch(aug_image, aug_bboxes, cats)
    for box in aug_bboxes:
        draw_bbox(img=aug_image, bbox=(box[0], box[1], box[2], box[3]))
    cv2.imshow("aug_image", aug_image)
    cv2.waitKey(0)


main()
