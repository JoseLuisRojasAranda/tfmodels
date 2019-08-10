import math
import cv2
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras.initializers import GlorotNormal
from tensorflow.keras.regularizers import l2
from ops.conv_ops import normal_conv, depthwise_conv, pointwise_conv, ReLU6
# Regresar un directoria para poder acceder modulo de otra carpeta
import sys
sys.path.append("..")
from utils import tfrecord_coco
sys.path.append("ops/")

class ssd_lite_conv(layers.Layer):
    # Args:
    #   filters: numero de filtros que se aplica en total
    #   kernel: tamaño del kernel
    def __init__(self, filters, kernel=(3, 3), name="ssd_lite_conv", **kwargs):
        super(ssd_lite_conv, self).__init__(name=name, **kwargs)
        self.filters = filters
        self.kernel = kernel

        self.dwise = depthwise_conv(self.kernel, strides=[1, 1, 1, 1],
                padding="SAME", name=name+"_dwise_conv")
        self.dwbn = layers.BatchNormalization(name=name+"_dwise_bn")
        self.dwrelu6 = ReLU6(name=name+"_dwise_relu6")

        self.pwise = pointwise_conv(self.filters)

    def get_config(self):
        config = super(ssd_lite_conv, self).get_config()
        config.update({
            "filters": self.filters,
            "kernel": self.kernel})

        return config

    def call(self, inputs, training=None):
        x = self.dwise(inputs)
        x = self.dwbn(inputs)
        x = self.dwrelu6(inputs)
        x = self.pwise(inputs)

        return x


class SSD_layer(layers.Layer):
    #
    # Constructor de la layer
    # Args:
    #   classes: cantidad de categorias a clasificar
    #   priors: el numero de priors de cada feature
    def __init__(self,
                 classes=3,
                 aspect_ratios=[1, 2, 3, 1/2, 1/3],
                 num_fmap=1,
                 total_fmaps=3,
                 img_size=224,
                 initializer=None,
                 regularizer=None,
                 weight_decay=1e-4,
                 name="SSD_layer", **kwargs):
        super(SSD_layer, self).__init__(name=name, **kwargs)
        
        self.classes = classes
        self.aspect_ratios = aspect_ratios

        # calcula el numero de priors dependiendo de los aspect ratios
        # siguiendo la implemetacion del paper
        self.priors = compute_num_priors(aspect_ratios)
        
        self.num_fmap = num_fmap
        self.total_fmaps = total_fmaps
        self.img_size = img_size

        if initializer == None:
            self.w_initializer = GlorotNormal()
        else:
            self.w_initializer = initializer

        if regularizer == None:
            self.w_regularizer = l2(weight_decay)
        else:
            selw.w_regularizer = regularizer

        # Realiza la prediccion de la seguriada de la clase y del tipo
        # de bounding box
        self.conv_conf = ssd_lite_conv(self.priors*self.classes)
        """
        self.conv_conf = normal_conv(self.priors*self.classes, (3, 3), 
            name=name+"_conv_conf",
            padding="SAME")
        """

        # Realiza la prediccion del offset de las default box,
        # el numero de filtros es de num_priors * 4(dx,dy,dw,dh)
        self.conv_loc = ssd_lite_conv(self.priors*4)
        """
        self.conv_loc = normal_conv(self.priors*4, (3, 3),
                name=name+"_conv_loc",
                padding="SAME")
        """

    def get_config(self):
        config = super(SSD_layer, self).get_config()
        config.update({
            "classes": self.classes,
            "aspect_ratios": self.aspect_ratios,
            "num_fmap": self.num_fmap,
            "total_fmaps": self.total_fmaps,
            "img_size": self.img_size
        })

        return config

    
    # Recive el feature map y calcula lo siguiente:
    #   conf: tensor shape (batch, features, features, priors, classes)
    #   loc: tensor shape (batch, features, features, priors, 4(dx,dy,dw,dh)
    #   priors: tensor shape (features, features, priors, 4(cx, cy, w, h))
    # con eso se puede obtener, una version con todo junto para el loss
    #  shape[batch, features*features, priors, classes+4(dx, dy, dw, dh)+4(cx, cy, w h)]
    def call(self, inputs, training=None):
        b_size = inputs.get_shape().as_list()[0]
        features = inputs.get_shape().as_list()[1]

        conf = self.conv_conf(inputs)
        loc = self.conv_loc(inputs)
        bpriors = PriorsBoxes(batch_size=b_size, features=features, num_fmap=self.num_fmap,
                total_fmaps=self.total_fmaps, aspect_ratios=self.aspect_ratios,
                img_size=self.img_size)
        
        # reshape clasification de las convoluciones
        conf = tf.reshape(conf, [b_size, features*features,
            self.priors, self.classes])
        loc = tf.reshape(loc, [b_size, features*features,
            self.priors, 4])

        bpriors = tf.cast(bpriors, tf.float32)
        prediction = tf.concat([conf, loc, bpriors], -1)

        return prediction

#
# Metodo que calcula el numero de priors dependiendo de cuantos aspect ratios
# se usen
# Args:
#   aspect_ratios: arreglo de proporciones
# Returns:
#   priors: entero que representa el numero de default boxes
def compute_num_priors(aspect_ratios):
    priors = 0
    for ratio in aspect_ratios:
        priors += 1
        # en caso de ratio == 1, se agrega otro ratio
        if ratio == 1:
            priors += 1

    return priors

# Metodo que calcula los priorboxes de un feature map
# Args:
#   features: entero mxm de un feature map
#   num_fmap: number of feature map of m feature maps
#   total_fmaps: the total number of feature maps of the network
#   aspect_ratios: arreglo de proporciones
#   img_size: tamaño de la imagen original
# Returns:
#   Tensor with boxes loc of shape (features, features, priors, 4(x, y, w, h))
@tf.function
def PriorsBoxes(batch_size=None,
                features=None,
                num_fmap=None,
                total_fmaps=None,
                aspect_ratios=None,
                img_size=None):

    # metodo de calcula la escala de las cajas
    def compute_scale(k, m):
        s_min = 0.2
        s_max = 0.9
        s_k = s_min + (((s_max - s_min)/(m - 1))*(k - 1))

        return s_k
    
    # calcula el ancho y alto de una caja segun su escala y proporcion
    def box_size(scale, aspect_ratio):
        h = scale/math.sqrt(aspect_ratio)
        w = scale*math.sqrt(aspect_ratio)

        return h, w

    s_k = compute_scale(num_fmap, total_fmaps)
    priors = 0
    heights = []
    widths = []

    # Calcula los tamaños de las bounding boxes
    for ar in aspect_ratios:
        priors += 1
        bh, bw = box_size(s_k, ar)
        heights.append(bh)
        widths.append(bw)

        # cuando el ratio es 1, se calcual otro segun el paper
        if ar == 1:
            priors += 1
            s_k_p = compute_scale(num_fmap+1, total_fmaps)
            bh, bw = box_size(s_k_p, ar)
            heights.append(bh)
            widths.append(bw)


    default_boxes = np.zeros((features, features, priors, 4))

    cell_size = 1 / features
    cell_center = cell_size / 2
    for i in range(features):
        for j in range(features):
            for p in range(priors):
                h, w = heights[p], widths[p]
                x = j*cell_size + cell_center
                y = i*cell_size + cell_center

                default_boxes[i, j, p, 0] = x
                default_boxes[i, j, p, 1] = y
                default_boxes[i, j, p, 2] = w
                default_boxes[i, j, p, 3] = h

    default_boxes *= img_size
    default_boxes = tf.convert_to_tensor(default_boxes)
   
    # Checa si se especifico un batch_size en los parametros
    # si si, agrega una dimension y duplica las otras mediante tiling
    if batch_size == None:
        return default_boxes 
    else:
        default_boxes = tf.reshape(default_boxes, [features*features, priors, 4])
        default_boxes = tf.expand_dims(default_boxes, 0)
        default_boxes = tf.tile(default_boxes, [batch_size, 1, 1, 1])

        return default_boxes

#
# Convirte cordenadas (cx,cy,w,h) a (x,y,w,h)
# Args:
#   loc: tensorf of shape [4]
# Returns:
#   x, y, w, h: posicion y tamaño como enteros
@tf.function
def bbox_center_to_rect(loc):
    w = loc[2]
    h = loc[3]
    x = loc[0] - (w/2)
    y = loc[1] - (h/2)

    return int(x), int(y), int(w), int(h)
#
# Converte cordenadas (x, y, w, h) a (cx, cy, w, h)
# Args:
#   loc: tensor of shape [4]
# Returns:
#   cx, cy, w, h: posicion y tamaño como enteros
@tf.function
def bbox_rect_to_center(loc):
    w = loc[2]
    h = loc[3]
    cx = loc[0] + (w/2)
    cy = loc[1] + (h/2)

    return int(x), int(y), int(w), int(h)

#
# Calcula el jaccard overlap o intesection over union IOU
# entre dos bounding boxes
# Args:
#   t_boxA: tensor of shape [4] de (x, y, w, h)
#   t_boxB: tensor of shape [4] de (x, y, w, h)
# Returns:
#   iou = float de 0.0 a 1.0
@tf.function
def intersection_over_union(t_boxA, t_boxB):
    # Se convierte los tensores  a numpy arrays
    boxA = np.array(t_boxA)
    boxB = np.array(t_boxB)
    
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA + 1) * max(0, yB - yA + 1)

    boxAArea = (boxA[2] - boxA[0] + 1) * (boxA[3] - boxA[1] + 1)
    boxBArea = (boxB[2] - boxB[0] + 1) * (boxB[3] - boxB[1] + 1)

    iou = interArea / float(boxAArea + boxBArea - interArea)

    return iou


# Pipeline encargada de procesar un batch de training set, para
# realizar la estrategia de matching para crear la informacion de
# ground truth
class SSD_data_pipeline(object):
    # Metodos del objeto
    #   init: iniicalizacion con los parametros de la arquitectura
    #   process: procesa un batch de imagenes

    # Inicializacion de los parametros acerca de la arquitectura de la red
    # Argumentos:
    #   aspect_ratios: arreglo conteniendo los aspect ratios segun el paper
    #   feature_maps: arreglo conteniendo pares con los tamaños de los f maps
    #   categories_arr: arreglo de strings con los nombre de las categorias
    #   img_size: entero que contiene el numero de pixeles de un lado de la img
    def __init__(self, 
                 aspect_ratios=[1, 2, 3, 1/2, 1/3], 
                 feature_maps=None, 
                 categories_arr=None,
                 img_size=None):
        self.aspect_ratios = aspect_ratios
        self.feature_maps = feature_maps
        self.categories_arr = categories_arr
        self.img_size = img_size
        self.num_priors = compute_num_priors(aspect_ratios)

        self.categories_index = {}
        # Creacion de indices de las categorias
        for i in range(len(self.categories_arr)):
            self.categories_index[self.categories_arr[i]] = i

    # Procesa un batch de imagenes para convertirlos a training data
    # Argumentos:
    #   image_batch: tensor de shape [batch_size, size, size, r, g, b]
    #   y_true: tensor de shape [batch_size, categorias + 4]
    def process(self, image_batch, y_true):
        pass

    def preprocess_tfrecord_coco(self, path_to_tfrecord):
        dataset_tfrecord_coco = tfrecord_coco.parse_dataset(path_to_tfrecord)
        
        it = iter(dataset_tfrecord_coco)

        for _ in range(3):
            img_data = next(it)

            # Decodificacion de imagen
            image_string = np.frombuffer(img_data["img/str"].numpy(), np.uint8)
            decoded_image = cv2.imdecode(image_string, cv2.IMREAD_COLOR)
            image_tensor = tf.convert_to_tensor(decoded_image)
            
            print(image_tensor)

            total_fmaps = len(self.feature_maps)
            for f_map in self.feature_maps:
                pass
        
