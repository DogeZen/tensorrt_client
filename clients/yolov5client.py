
import argparse
import numpy as np
import sys
import cv2

import tritonclient.grpc as grpcclient
from tritonclient.utils import InferenceServerException

from processing import preprocess, postprocess
from render import render_box, render_filled_box, get_text_size, render_text, RAND_COLORS
from labels import COCOLabels

import time
import multiprocessing
from multiprocessing import Pool
import os
class yolov5client():
    url = '192.168.1.221:8001'
    model = 'yolov5l-3'
    ssl = False
    root_certificates = None
    private_key = None
    certificate_chain = None
    client_timeout = None
    nms = 0.4
    model_info = False
    verbose = False

    def __init__(self):
        # Create server context
        try:
            triton_client = grpcclient.InferenceServerClient(
                url=self.url,
                verbose=self.verbose,
                ssl=self.ssl,
                root_certificates=self.root_certificates,
                private_key=self.private_key,
                certificate_chain=self.certificate_chain)
        except Exception as e:
            print("context creation failed: " + str(e))
            sys.exit()

        # Health check
        if not triton_client.is_server_live():
            print("FAILED : is_server_live")
            sys.exit(1)

        if not triton_client.is_server_ready():
            print("FAILED : is_server_ready")
            sys.exit(1)

        if not triton_client.is_model_ready(self.model):
            print("FAILED : is_model_ready",self.model)
            sys.exit(1)


        try:
            metadata = triton_client.get_model_metadata(self.model)
            print(metadata)
        except InferenceServerException as ex:
            if "Request for unknown model" not in ex.message():
                print("FAILED : get_model_metadata")
                print("Got: {}".format(ex.message()))
                sys.exit(1)
            else:
                print("FAILED : get_model_metadata")
                sys.exit(1)

        # Model configuration
        try:
            config = triton_client.get_model_config(self.model)
            if not (config.config.name == self.model):
                print("FAILED: get_model_config")
                sys.exit(1)
            # print(config)
        except InferenceServerException as ex:
            print("FAILED : get_model_config")
            print("Got: {}".format(ex.message()))
            sys.exit(1)

        self. triton_client = triton_client




    def infer(self,input_img,triton_client,confidence = 0.5):
        confidence = confidence
        out = "output/"+input_img.split("/")[1]
        # IMAGE MODE
        # print("Running in 'image' mode")
        if not input_img:
            print("FAILED: no input image")
            sys.exit(1)
        
        inputs = []
        outputs = []
        inputs.append(grpcclient.InferInput('data', [1, 3, 640, 640], "FP32"))
        outputs.append(grpcclient.InferRequestedOutput('prob'))

        # print("Creating buffer from image file...")
        input_image = cv2.imread(input_img)
        if input_image is None:
            print(f"FAILED: could not load input image {str(input_img)}")
            sys.exit(1)
        input_image_buffer,dw,dh,padding_w,padding_h= preprocess(input_image)
        input_image_buffer = np.expand_dims(input_image_buffer, axis=0)
        inputs[0].set_data_from_numpy(input_image_buffer)

        # print("Invoking inference...")
        results = self.triton_client.infer(model_name=self.model,
                                    inputs=inputs,
                                    outputs=outputs,
                                    client_timeout=self.client_timeout)
        if self.model_info:
            statistics = self.triton_client.get_inference_statistics(model_name=self.model)
            if len(statistics.model_stats) != 1:
                print("FAILED: get_inference_statistics")
                sys.exit(1)
            # print(statistics)
        # print("load model done")

        result = results.as_numpy('prob')
        # print(f"Received result buffer of size {result.shape}")
        # print(f"Naive buffer sum: {np.sum(result)}")

        detected_objects = postprocess(result, input_image.shape[1], input_image.shape[0],dw,dh,padding_w,padding_h,confidence, self.nms)
        print(f"Raw boxes: {int(result[0, 0, 0, 0])}")
        print(f"Detected objects: {len(detected_objects)}")

        return_info = []

        for box in detected_objects:
            return_info.append([box.classID,box.u1,box.u2,box.v1,box.v2])
            print(f"{COCOLabels(box.classID).name}: {box.confidence}")
            input_image = render_box(input_image, box.box(), color=tuple(RAND_COLORS[box.classID % 64].tolist()))
            size = get_text_size(input_image, f"{COCOLabels(box.classID).name}: {box.confidence:.2f}", normalised_scaling=0.6)
            input_image = render_filled_box(input_image, (box.x1 - 3, box.y1 - 3, box.x1 + size[0], box.y1 + size[1]), color=(220, 220, 220))
            input_image = render_text(input_image, f"{COCOLabels(box.classID).name}: {box.confidence:.2f}", (box.x1, box.y1), color=(30, 30, 30), normalised_scaling=0.5)

        if out:
            cv2.imwrite(out, input_image)
            print(f"Saved result to {out}")
        else:
            cv2.imshow('image', input_image)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return return_info

