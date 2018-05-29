import os.path
import tensorflow as tf
import helper
import warnings
from distutils.version import LooseVersion
import project_tests as tests


# Check TensorFlow Version
assert LooseVersion(tf.__version__) >= LooseVersion('1.0'), 'Please use TensorFlow version 1.0 or newer.  You are using {}'.format(tf.__version__)
print('TensorFlow Version: {}'.format(tf.__version__))

# Check for a GPU
if not tf.test.gpu_device_name():
    warnings.warn('No GPU found. Please use a GPU to train your neural network.')
else:
    print('Default GPU Device: {}'.format(tf.test.gpu_device_name()))


def load_vgg(sess, vgg_path):
    """
    Load Pretrained VGG Model into TensorFlow.
    :param sess: TensorFlow Session
    :param vgg_path: Path to vgg folder, containing "variables/" and "saved_model.pb"
    :return: Tuple of Tensors from VGG model (image_input, keep_prob, layer3_out, layer4_out, layer7_out)
    """
    #   Use tf.saved_model.loader.load to load the model and weights
    vgg_tag = 'vgg16'
    vgg_input_tensor_name = 'image_input:0'
    vgg_keep_prob_tensor_name = 'keep_prob:0'
    vgg_layer3_out_tensor_name = 'layer3_out:0'
    vgg_layer4_out_tensor_name = 'layer4_out:0'
    vgg_layer7_out_tensor_name = 'layer7_out:0'
    tf.saved_model.loader.load(sess, [vgg_tag], vgg_path)
    graph = tf.get_default_graph()
    vgg_input = graph.get_tensor_by_name(vgg_input_tensor_name)
    keep_prob = graph.get_tensor_by_name(vgg_keep_prob_tensor_name)
    vgg_layer3 = graph.get_tensor_by_name(vgg_layer3_out_tensor_name)
    vgg_layer4 = graph.get_tensor_by_name(vgg_layer4_out_tensor_name)
    vgg_layer7 = graph.get_tensor_by_name(vgg_layer7_out_tensor_name)

    return vgg_input, keep_prob, vgg_layer3, vgg_layer4, vgg_layer7
tests.test_load_vgg(load_vgg, tf)

def conv_1x1(inputs,
             filters):
    return tf.layers.conv2d(inputs,
                            filters,
                            kernel_size=1,
                            strides=(1, 1),
                            padding='same',
                            kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))

def up_sample(inputs,
              filters,
              kernel_size,
              strides):
    return tf.layers.conv2d_transpose(inputs,
                                      filters,
                                      kernel_size,
                                      strides,
                                      padding='same',
                                      kernel_regularizer=tf.contrib.layers.l2_regularizer(1e-3))

def print_info(input):
    tf.Print(input, [tf.shape(input)], message="Shape of input:", summarize=10, first_n=1)

def layers(vgg_layer3_out, vgg_layer4_out, vgg_layer7_out, num_classes):
    """
    Create the layers for a fully convolutional network.  Build skip-layers using the vgg layers.
    :param vgg_layer3_out: TF Tensor for VGG Layer 3 output
    :param vgg_layer4_out: TF Tensor for VGG Layer 4 output
    :param vgg_layer7_out: TF Tensor for VGG Layer 7 output
    :param num_classes: Number of classes to classify
    :return: The Tensor for the last layer of output
    """
    vgg_layer7_out = conv_1x1(vgg_layer7_out, num_classes)
    vgg_layer7_out = up_sample(vgg_layer7_out,
                               num_classes,
                               kernel_size=4,
                               strides=(2, 2))
    print_info(vgg_layer7_out)

    vgg_layer4_out = conv_1x1(vgg_layer4_out, num_classes)
    vgg_layer4_out = tf.multiply(vgg_layer4_out, 1e-2)
    vgg_layer_7_and_4 = tf.add(vgg_layer7_out, vgg_layer4_out)
    vgg_layer_7_and_4 = up_sample(vgg_layer_7_and_4,
                                  num_classes,
                                  kernel_size=4,
                                  strides=(2, 2))
    print_info(vgg_layer_7_and_4)

    vgg_layer3_out = conv_1x1(vgg_layer3_out, num_classes)
    vgg_layer3_out = tf.multiply(vgg_layer3_out, 1e-4)
    vgg_layer_7_and_4_and_3 = tf.add(vgg_layer3_out, vgg_layer_7_and_4)
    output = up_sample(vgg_layer_7_and_4_and_3,
                       num_classes,
                       kernel_size=16,
                       strides=(8, 8))
    print_info(output)

    return output
tests.test_layers(layers)


def optimize(nn_last_layer, correct_label, learning_rate, num_classes):
    """
    Build the TensorFLow loss and optimizer operations.
    :param nn_last_layer: TF Tensor of the last layer in the neural network
    :param correct_label: TF Placeholder for the correct label image
    :param learning_rate: TF Placeholder for the learning rate
    :param num_classes: Number of classes to classify
    :return: Tuple of (logits, train_op, cross_entropy_loss)
    """
    logits = tf.reshape(nn_last_layer, (-1, num_classes))
    correct_label = tf.reshape(correct_label, (-1, num_classes))

    im_softmax = tf.nn.softmax(logits)
    predictions = im_softmax > 0.5
    predictions = tf.reshape(predictions, (-1, num_classes))

    # iou, iou_op = tf.metrics.mean_iou(labels=correct_label,
    #                                   predictions=predictions,
    #                                   num_classes=num_classes)
    iou, iou_op = None, None


    cross_entropy_loss = tf.reduce_mean(
            tf.nn.softmax_cross_entropy_with_logits(logits=logits,
                                                labels=correct_label))
    optimizer = tf.train.AdamOptimizer(learning_rate = learning_rate)
    training_operation = optimizer.minimize(cross_entropy_loss)

    return logits, training_operation, cross_entropy_loss, iou, iou_op
tests.test_optimize(optimize)


def train_nn(sess, epochs, batch_size, get_batches_fn, train_op, cross_entropy_loss, input_image,
             correct_label, keep_prob, learning_rate, iou, iou_op):
    """
    Train neural network and print out the loss during training.
    :param sess: TF Session
    :param epochs: Number of epochs
    :param batch_size: Batch size
    :param get_batches_fn: Function to get batches of training data.  Call using get_batches_fn(batch_size)
    :param train_op: TF Operation to train the neural network
    :param cross_entropy_loss: TF Tensor for the amount of loss
    :param input_image: TF Placeholder for input images
    :param correct_label: TF Placeholder for label images
    :param keep_prob: TF Placeholder for dropout keep probability
    :param learning_rate: TF Placeholder for learning rate
    """
    sess.run(tf.global_variables_initializer())
    sess.run(tf.local_variables_initializer())
    if (iou_op is not None):
        sess.run(iou_op)

    print("Training...")

    for epoch in range(epochs):
        for image, label in get_batches_fn(batch_size):
            train_feed_dict = {
                correct_label: label,
                keep_prob: 0.8,
                learning_rate: 0.001,
                input_image: image
            }


            _, loss = sess.run([train_op, cross_entropy_loss],
                            feed_dict=train_feed_dict)
            mean_iou = None

            # _, loss, mean_iou = sess.run([train_op, cross_entropy_loss, iou],
            #                 feed_dict=train_feed_dict)

            print('epoch: [{epoch}] loss: [{loss}]'.format(
                epoch=epoch, loss=loss))
tests.test_train_nn(train_nn)


def run():
    num_classes = 2
    image_shape = (160, 576)
    data_dir = './data'
    runs_dir = './runs'

    batch_size = 10
    epochs = 6
    learning_rate = tf.placeholder(tf.float32, None)

    tests.test_for_kitti_dataset(data_dir)

    # Download pretrained vgg model
    helper.maybe_download_pretrained_vgg(data_dir)

    # OPTIONAL: Train and Inference on the cityscapes dataset instead of the Kitti dataset.
    # You'll need a GPU with at least 10 teraFLOPS to train on.
    #  https://www.cityscapes-dataset.com/

    correct_label = tf.placeholder(tf.int32, (None,
                                                image_shape[0],
                                                image_shape[1],
                                                num_classes))

    with tf.Session() as sess:
        # Path to vgg model
        vgg_path = os.path.join(data_dir, 'vgg')
        # Create function to get batches
        get_batches_fn = helper.gen_batch_function(os.path.join(data_dir, 'data_road/training'), image_shape)

        # OPTIONAL: Augment Images for better results
        #  https://datascience.stackexchange.com/questions/5224/how-to-prepare-augment-images-for-neural-network

        vgg_input, keep_prob, vgg_layer3, vgg_layer4, vgg_layer7 = load_vgg(sess, vgg_path)

        output = layers(vgg_layer3, vgg_layer4, vgg_layer7, num_classes)

        logits, training_operation, cross_entropy_loss, iou, iou_op = optimize(output,
                                                                  correct_label,
                                                                  learning_rate,
                                                                  num_classes)
        train_nn(sess,
                 epochs,
                 batch_size,
                 get_batches_fn,
                 training_operation,
                 cross_entropy_loss,
                 vgg_input,
                 correct_label,
                 keep_prob,
                 learning_rate,
                 iou,
                 iou_op)

        helper.save_inference_samples(runs_dir,
                                      data_dir,
                                      sess,
                                      image_shape,
                                      logits,
                                      keep_prob,
                                      vgg_input)

        # OPTIONAL: Apply the trained model to a video


if __name__ == '__main__':
    run()
