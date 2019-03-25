import numpy as np
import tensorflow as tf
import cv2
import imutils
from collections import defaultdict
from cropper.object_detection.utils import ops as utils_ops
from cropper.object_detection.utils import label_map_util
from cropper.object_detection.utils import visualization_utils as vis_util
from cropper.transform import four_point_transform
from matplotlib import pyplot as plt
import copy


def plot_img(img):
    plt.imshow(img)
    plt.show()


def load_image_into_numpy_array(image):
    (im_width, im_height) = image.size
    return np.array(image.getdata()).reshape(
        (im_height, im_width, 3)).astype(np.uint8)


def run_inference_for_single_image(image, graph):
    with graph.as_default():
        with tf.Session() as sess:
            # Get handles to input and output tensors
            ops = tf.get_default_graph().get_operations()
            all_tensor_names = {
                output.name for op in ops for output in op.outputs}
            tensor_dict = {}
            for key in [
                'num_detections', 'detection_boxes', 'detection_scores',
                'detection_classes', 'detection_masks'
            ]:
                tensor_name = key + ':0'
                if tensor_name in all_tensor_names:
                    tensor_dict[key] = tf.get_default_graph().get_tensor_by_name(
                        tensor_name)
            if 'detection_masks' in tensor_dict:
                # The following processing is only for single image
                detection_boxes = tf.squeeze(
                    tensor_dict['detection_boxes'], [0])
                detection_masks = tf.squeeze(
                    tensor_dict['detection_masks'], [0])
                # Reframe is required to translate mask from box coordinates to image coordinates
                # and fit the image size.
                real_num_detection = tf.cast(
                    tensor_dict['num_detections'][0], tf.int32)
                detection_boxes = tf.slice(detection_boxes, [0, 0], [
                                           real_num_detection, -1])
                detection_masks = tf.slice(detection_masks, [0, 0, 0], [
                                           real_num_detection, -1, -1])
                detection_masks_reframed = utils_ops.reframe_box_masks_to_image_masks(
                    detection_masks, detection_boxes, image.shape[0], image.shape[1])
                detection_masks_reframed = tf.cast(
                    tf.greater(detection_masks_reframed, 0.5), tf.uint8)
                # Follow the convention by adding back the batch dimension
                tensor_dict['detection_masks'] = tf.expand_dims(
                    detection_masks_reframed, 0)
            image_tensor = tf.get_default_graph().get_tensor_by_name('image_tensor:0')
            output_dict = sess.run(tensor_dict,
                                   feed_dict={image_tensor: np.expand_dims(image, 0)})

            # all outputs are float32 numpy arrays, so convert types as appropriate
            output_dict['num_detections'] = int(
                output_dict['num_detections'][0])
            output_dict['detection_classes'] = output_dict[
                'detection_classes'][0].astype(np.uint8)
            output_dict['detection_boxes'] = output_dict['detection_boxes'][0]
            output_dict['detection_scores'] = output_dict['detection_scores'][0]
            if 'detection_masks' in output_dict:
                output_dict['detection_masks'] = output_dict['detection_masks'][0]
    return output_dict


def load_model(model_name):
    MODEL_NAME = model_name
    PATH_TO_FROZEN_GRAPH = 'cropper/' + MODEL_NAME + '/frozen_inference_graph.pb'
    detection_graph = tf.Graph()
    with detection_graph.as_default():
        od_graph_def = tf.GraphDef()
        with tf.gfile.GFile(PATH_TO_FROZEN_GRAPH, 'rb') as fid:
            serialized_graph = fid.read()
            od_graph_def.ParseFromString(serialized_graph)
            tf.import_graph_def(od_graph_def, name='')
    return detection_graph


def find_missing_element(L):
    for i in range(1, 5):
        if i not in L:
            return i


def get_conner_locations(img, model_name):
    detection_graph = load_model(model_name)
    output_dict = run_inference_for_single_image(img, detection_graph)
    boxes = output_dict['detection_boxes']
    im_height, im_width, _ = img.shape
    conner_location = []
    for i in range(boxes.shape[0]):
        if output_dict['detection_scores'][i] > 0.5:
            ymin, xmin, ymax, xmax = tuple(boxes[i].tolist())
            (left, right, top, bottom) = (int(xmin * im_width), int(xmax * im_width),
                                          int(ymin * im_height), int(ymax * im_height))
            conner_middle_point = ((left + right) // 2, (top + bottom) // 2)
            location_index = output_dict['detection_classes'][i]
            conner_location.append((conner_middle_point, location_index))
    return conner_location


def get_card(img, model_name):
    detection_graph = load_model(model_name)
    output_dict = run_inference_for_single_image(img, detection_graph)
    boxes = output_dict['detection_boxes']
    im_height, im_width, _ = img.shape
    conner_location = []
    for i in range(boxes.shape[0]):
        if output_dict['detection_scores'][i] > 0.5:
            ymin, xmin, ymax, xmax = tuple(boxes[i].tolist())
            return (int(xmin * im_width), int(xmax * im_width),
                    int(ymin * im_height), int(ymax * im_height))


def remove_conner(list_conner, rectangle):
    list_orig = copy.deepcopy(list_conner)
    left, right, top, bottom = rectangle
    for conner in list_orig:
        if conner[0] < left or conner[0] > right or conner[1] < top or conner[1] > bottom:
            list_conner.remove(conner)
    return list_conner


def resize_img(img):
    h, w, _ = img.shape
    max_dim = min(h, w)
    ratio = 1
    if max_dim <= 500:
        return (img, ratio)
    if max_dim == h:
        ratio = img.shape[0] / 500.0
        img = imutils.resize(img, height=500)
    if max_dim == w:
        ratio = img.shape[1] / 500.0
        img = imutils.resize(img, width=500)
    return (img, ratio)


def crop_card(image_path):
    img = cv2.imread(image_path)
    orig = img.copy()
    img, ratio = resize_img(img)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    conner_location = get_conner_locations(img, 'mon_graphs')
    list_conner = [conner[0] for conner in conner_location]
    if len(list_conner) == 3:
        list_index = [conner[1] for conner in conner_location]
        missing_element = find_missing_element(list_index)
        missing_conner = (0, 0)
        for conner in conner_location:
            x, y = conner[0]
            if (conner[1] + missing_element) != 5:
                missing_conner = (missing_conner[0] + x, missing_conner[1] + y)
            else:
                missing_conner = (missing_conner[0] - x, missing_conner[1] - y)
        list_conner.append(missing_conner)
    if len(list_conner) > 4:
        rectangle = get_card(img, 'card_graphs')
        list_conner = remove_conner(list_conner, rectangle)
    pts = np.array(list_conner, dtype="float32")
    warped = four_point_transform(orig, pts * ratio)
    return warped
