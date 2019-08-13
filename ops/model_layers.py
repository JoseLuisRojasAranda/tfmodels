
# Script con classes para el manejo de las layer de un modelo
# TODO:
#   * Permitir extrar partes de la red para crear nuevas redes

# Clase para elementos de la lista con las capas del modelo
class LayerRef():
    # Args:
    #   layer: keras layer class que computa la entrada
    #   only_training: si solo se llama cuando esta en fase de entrenamiento
    #   save_output: si se va a guardar el output de la layer
    #   output_index: el indice de la lista de outputs
    #   custom_input: cadena para diccionario de layers guardadas
    #   custom_input_index: indice del output de una layer guardada
    def __init__(self, layer, 
            only_training=False, 
            save_output=False,
            output_index=-1,
            custom_input=None,
            custom_input_index=-1):
        self.layer = layer
        self.only_training = only_training
        self.save_output = save_output
        self.output_index = output_index
        self.custom_input = custom_input
        self.custom_input_index = custom_input_index
        self.outputs = []

    # Args:
    #   inputs: tensor con input al layer
    #   training: si el modelo esta en fase de entrenamiento
    #   output_index: cual es el output en la lista (-1 ultimo)
    # Returns:
    #   x: tensor con resultado de la layer
    def __call__(self, inputs, training=False):
        if not training and self.only_training:
            return inputs
        else:
            x = self.layer(inputs, training=training)
            if type(x) is not list:
                x = [x]

            if self.save_output:
                self.outputs = x

            return x[self.output_index]
#
# Estructura de dato que nos permite guardar las referencias a las layers
# de un modelo de una red neuronal, todo la implementacion es siguiendo el
# API de keras para las layers. Permite las siguientes funcionalidades
#   - Guardar los outputs de ciertas layers
#   - Que el input de una layer sea el output de una layer guardada
#   - Tener acceso a las layers mediante indices y diccionarios
#   - Feedforward
class LayerList():
    def __init__(self):
        self.layers_list = []
        self.layers_dict = {}
        self.saved_ref = {}

    # Agrega un layer a la lista
    # Args:
    #   layers: keras Layer que realiza la computacion
    #   only_training: si solo se llama durante entrenamiento
    #   save_as: string que guarda en un dict el output, None no guarda
    #   output_index: del output del layer(lista) cual es el indice que se usa
    #   custom_input: string del nombre del output que se guarda para input
    #   custom_input_index: del input guarda cual es el indice
    def add(self, layer, 
            only_training=False, 
            save_as=None,
            output_index=-1,
            custom_input=None,
            custom_input_index=-1):
        save_output = False if save_as == None else True
        l = LayerRef(layer, only_training=only_training,
                save_output=save_output,
                output_index=output_index,
                custom_input=custom_input,
                custom_input_index=custom_input_index)
        
        self.layers_list.append(l)
        if layer.name != None:
            self.layers_dict[layer.name] = (len(self.layers_list)-1, l)
        if save_output:
            self.saved_ref[save_as] = l

    # Realiza feed forward en las layers
    def feed_forward(self, inputs, training=None):
        x = inputs
        print(x.get_shape())

        for layer in self.layers_list:
            # Si hay input especial
            if layer.custom_input != None:
                x = self.saved_ref[layer.custom_input].outputs[layer.custom_input_index]

            x = layer(x, training)
            print(layer.layer.name)
            print(x.get_shape())

        return x

    # Regresa cuantas layers tiene la lista
    def __len__(self):
        return len(self.layers_list)


