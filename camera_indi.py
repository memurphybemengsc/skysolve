#!/usr/bin/env python3

# below is for introspection
import inspect
import sys

import argparse
import os
import re
import sys
import time
import threading
import numpy as np
from pathlib import Path
from PIL import Image
from astropy.io import fits
import img_scale

import PyIndi

# I don't think I need this but I'll leave it here for now
class skyCameraINDI():
    camera = None
    shutter = 1000000
    ISO=800
    resolution= (2000,1500)
    format = 'fits'
    
    def __init__(self, skystatus, shutter=.9, ISO=800, resolution=(2000,1500), format = 'fits'):
        self.skyStatus = skystatus
        self.camera = IndiCameraClient()
        
# https://pypi.org/project/pyindi-client/

class IndiCameraClient(PyIndi.BaseClient):
    indiHost = "localhost"
    indiPort = 7624
    indiClient = None
    isIndiConnected = False
    isCameraConnected = False
    indiCameraName = ""
    indiCameraDevice = None
    exposureInSeconds = 1
    
    # These are placeholders for now, used in status method
    shutter_speed = 1000000
    cameraResolutionX = 0
    cameraResolutionY = 0
    camera = None
    fullImageName = None
    
    def __init__(self):
        #super().__init__()
        super(IndiCameraClient, self).__init__()
        self.image_received = threading.Event()
        self.image_path = None
        self.image_error = None
                        
    def setHost(self, host):
        self.indiHost = host
        
    def setIndiPort(self, port):
        self.indiPort = port

    def connectToIndiServer(self):
        self.indiClient = IndiCameraClient()
        self.indiClient.output_file = "capture.fits"

        self.indiClient.setServer(self.indiHost, self.indiPort)

        print(f"Connecting to INDI server {self.indiHost}:{self.indiPort}...")
        if not self.indiClient.connectServer():
            print(f"Cannot connect to INDI server at {self.indiHost}:{self.indiPort}")
            self.isIndiConnected = False
            self.isCameraConnected = False
        else:
            print(f"We have connected to INDI server at {self.indiHost}:{self.indiPort}")
            self.isIndiConnected = True
            #Include a delay to allow for device handshakes
            time.sleep(2)
            
    def disconnectFromIndiServer(self):
        if self.isIndiConnected:
            self.indiClient.disconnectServer()
            self.isIndiConnected = False

    def connectCamera(self):
        # Are we connected to Indi? Return if not
        if not self.isIndiConnected:
            self.isCameraConnected = False
            return
        if self.isCameraConnected:
            return

        #print("connectCamera - we are connected to indi",self.indiClient.getHost(),":",self.indiClient.getPort())
        print(f"connectCamera - We are connected to INDI server at {self.indiClient.getHost()}:{self.indiClient.getPort()}")
        #print(type(self.indiClient))
        # Collect all devices currently known to the client.
        devices = list(self.indiClient.getDevices())
        #print("devices", devices)

        # Standard INDI camera devices normally expose CCD_INFO or CCD_EXPOSURE properties.
        self.isCameraConnected = False
        self.indiCameraName = ""
        self.indiCameraDevice = None
        for device in devices:
            print("device:", device.getDeviceName())
            # Connect to device if not connected
            deviceConnection = device.getProperty("CONNECTION")
            if deviceConnection:
                if deviceConnection.getState() != PyIndi.IPS_OK:
                    # Device is not connect so connect
                    self.indiClient.connectDevice(device.getDeviceName())
                    # Allow the device time to connect
                    time.sleep(1)
            if (
                device.getProperty("CCD_INFO")
                or device.getProperty("CCD_EXPOSURE")
            ):
                self.isCameraConnected = True
                self.indiCameraName = device.getDeviceName()
                self.indiCameraDevice = device
                
                # configure image capture
                # Options: B_NEVER, B_ALSO (Send BLOBs), B_ONLY
                self.indiClient.setBLOBMode(PyIndi.B_ALSO, self.indiCameraName, None)
                self.indiClient.enableDirectBlobAccess(self.indiCameraName, None)
                
                # We have found one device so return
                return
        
    def populateResolution(self):
        if self.isIndiConnected and self.isCameraConnected:
            ccd_info = self.indiCameraDevice.getNumber("CCD_INFO")
            if ccd_info is None or len(ccd_info) == 0:
                self.cameraResolutionX = 0
                self.cameraResolutionY = 0
            else:
                self.cameraResolutionX = ccd_info.findWidgetByName("CCD_MAX_X").getValue()
                self.cameraResolutionY = ccd_info.findWidgetByName("CCD_MAX_Y").getValue()
        else:
            self.cameraResolutionX = 0
            self.cameraResolutionY = 0

    def getCfaInfo(self):
        if self.isIndiConnected and self.isCameraConnected:
            cfa = self.camera.getText("CCD_CFA")
            if cfa is None or cfa == "":
                raise RuntimeError("CCD_CFA property unavailable")
            else:
                print("CFA_OFFSET_X is", cfa.findWidgetByName("CFA_OFFSET_X").getText());
                print("CFA_OFFSET_Y is", cfa.findWidgetByName("CFA_OFFSET_Y").getText());
                print("CFA_TYPE is", cfa.findWidgetByName("CFA_TYPE").getText());

    def setISO(self, newISO):
        # The new ISO as an int. This will be gain in INDI speak
        if self.isIndiConnected and self.isCameraConnected:
            controls = self.indiCameraDevice.getNumber("CCD_CONTROLS")
            if controls is None:
                return
            gain_element = controls.findWidgetByName("Gain")
            if gain_element is None:
                return
            minimum = gain_element.getMin()
            maximum = gain_element.getMax()
            current = gain_element.getValue()
            if newISO > maximum:
                return
            if newISO < minumum:
                return
            gain_element.setValue(float(newISO))
            self.indiClient.sendNewNumber(controls)

    def status(self):
        #return [self.ISO, self.camera.shutter_speed, self.resolution]
        return ["INDI", "INDI", "INDI"]
    def setResolution(self,  size):
        pass
    def setFormat(self,type):
        pass
    def setShutter(self, value):
        pass
    def setupGain(self, value):
        pass

    def setExposure(self, exposureInSecs):
        self.exposureInSeconds = exposureInSecs
        
    def get_frame(self):
        # Take an image
        if self.isIndiConnected and self.isCameraConnected:
            # Wait for the exposure control to become available.
            self.indiClient.wait_for_property(self.indiCameraDevice, "CCD_EXPOSURE")
    
            exposure = self.indiCameraDevice.getNumber("CCD_EXPOSURE")
            #print(f"Camera exposure is currently {exposure[0].getValue()} setting to {self.exposureInSeconds}")
            if exposure is None or len(exposure) == 0:
                raise RuntimeError("CCD_EXPOSURE property unavailable")
    
            # Set a one-second exposure.
            exposure[0].setValue(self.exposureInSeconds)
            self.indiClient.sendNewNumber(exposure)
            
            # Wait for the image BLOB, allowing extra download time.
            if not self.indiClient.image_received.wait(timeout=90):
                print("Image received timeout")
                
            #print(f"Camera exposure is currently {exposure[0].getValue()} setting to {self.exposureInSeconds}")
            if self.indiClient.image_path is None:
                print("Image not taken")
            else:
                print(f"Image path is {self.indiClient.image_path}")
        

    # 12/10/2026, Added. Seems to be a new way to get blob. seems to be called.
    # Modern INDI Core 2.0+ pattern
    def updateProperty(self, prop):
        if prop.getType() == PyIndi.INDI_BLOB: # 13-10-2026 changed this to == from !=
            # Manually route it or handle it here
            self.newBLOB(PyIndi.PropertyBlob(prop)) # IndiCameraClient.newBLOB() 
            return

    def newBLOB(self, prop):        
        for blob in PyIndi.PropertyBlob(prop):
            try:
                data = blob.getblobdata()
                
                if not data:
                    continue # skip this loop iteration
    
                #print("type of data is", type(data))
                # Preserve the format advertised by the driver.
                image_format = blob.getFormat().lower()
                if not image_format.startswith("."):
                    image_format = "." + image_format
    
                # Avoid unsafe characters in the file extension.
                if not re.fullmatch(r"\.[a-z0-9.]+", image_format):
                    image_format = ".fits"
    
                output = Path(self.output_file)
                output = output.with_suffix(image_format)
                print("output is ", output)
    
                with open(output, "wb") as f:
                    f.write(data)
    
                self.image_path = output
                self.fullImageName = output
                print(f"fullImageName: {self.fullImageName}")
                print(f"Image saved: {output.resolve()}")
                fullName = output.resolve()
                prinf(f"fullName is {fullName}")
                print(f"Image size: {len(data)} bytes")
                self.image_received.set()
                print(f"Converting {self.fullImageName.resolve()} to jpg")
                #convertFitsToJpeg(self.fullImageName)
    
            except Exception as exc:
                self.image_error = exc
                self.image_received.set()

    # Used this github project to convert fits to jpeg
    # https://github.com/psds075/fitstoimg/blob/master/img_scale.py
    def convertFitsToJpeg(self):
        #print(f"convertFitsToJpeg - output_file: {self.output_file}")
        fitsFile = "capture.fits"
        jpegFile = "capture.jpg"
        image_data = fits.getdata(fitsFile)
        if len(image_data.shape) == 2:
            sum_image = image_data
        else:
            sum_image = image_data[0] - image_data[0]
            for single_image_data in image_data:
                sum_image += single_image_data  
                
        sum_image = img_scale.sqrt(sum_image, scale_min=0, scale_max=np.amax(image_data))
        sum_image = sum_image * 200
        im = Image.fromarray(sum_image)
        if im.mode != 'RGB':
            im = im.convert('RGB')
    
        im.save(jpegFile)
        im.close()
        
        
        
    def wait_for_property(self, device, name, timeout=15):
        """Wait until a device property becomes available."""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            prop = device.getProperty(name)
            if prop:
                return prop
            time.sleep(0.1)

        raise TimeoutError(
            f"Timed out waiting for INDI property {name!r}"
        )

# This method is porbably obsolete
def get_first_connected_camera(client, timeout=10):
    first_connected_camera = None
    if not client.isServerConnected():
        if not client.connectServer():
            raise ConnectionError(
                f"Could not connect to INDI server at {client.getHost()}:{client.getPort()}"
            )

    try:
        # Allow time for the server to publish its devices.
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            time.sleep(0.2)

            devices = list(client.getDevices())
            if devices:
                # Continue briefly to allow other devices to appear.
                break

        # Collect all devices currently known to the client.
        devices = list(client.getDevices())
        
        # connect to the devices
        for device in devices:
            deviceConnection = device.getProperty("CONNECTION")
            if deviceConnection:
                if deviceConnection.getState() == PyIndi.IPS_OK:
                    print("status is connected")
                else:
                    print("Status is disconnected - connecting device", device.getDeviceName())
                    client.connectDevice(device.getDeviceName())
                    # Allow time for the device to connect
                    time.sleep(1)
        

        # Standard INDI camera devices normally expose CCD_INFO
        # or CCD_EXPOSURE properties.
        cameras = []

        for device in devices:
            # Wait for the exposure control to become available.
            print("Getting CCD_EXPOSURE property for device", device.getDeviceName())
            client.wait_for_property(device, "CCD_EXPOSURE")
            
            if (
                device.getProperty("CCD_EXPOSURE")
            ):
                cameras.append(device)

        print("\n" + "=" * 60)
        print(f"INDI devices found: {len(devices)}")
        print(f"Camera devices found: {len(cameras)}")
        print("=" * 60)

        if not cameras:
            print(
                "No camera devices detected. "
                "Check that the camera driver is running."
            )
            print("\nAll available devices:")
            for device in devices:
                print(f"  - {device.getDeviceName()}")
            
            return

        for index, camera in enumerate(cameras, start=1):
            name = camera.getDeviceName()
            connection = camera.getProperty("CONNECTION")

            status = "Unknown"
            if connection:
                if connection.getState() == PyIndi.IPS_OK:
                    status = "Connected"
                elif connection.getState() == PyIndi.IPS_ALERT:
                    status = "Connection error"
                else:
                    switches = camera.getSwitch("CONNECTION")
                    if switches:
                        connect = switches.findWidgetByName("CONNECT")
                        if connect and connect.getState() == PyIndi.ISS_ON:
                            status = "Connected"
                        else:
                            status = "Not connected"

            print(f"\nCamera {index}:")
            print(f"  Name:   {name}")
            print(f"  Status: {status}") # Connected
            if status == "Connected" and not first_connected_camera:
                print("Assigning camera")
                first_connected_camera = camera

    finally:
        pass
    
    return first_connected_camera

# Return the current camera image full file name            
def capture(host, port):
    client = IndiCameraClient()
    client.output_file = "capture.fits"

    try:
        client.setServer(host, port)

        print(f"Connecting to INDI server {host}:{port}...")
        if not client.connectServer():
            raise ConnectionError(
                f"Cannot connect to INDI server at {host}:{port}"
            )

        # Wait for the requested camera to appear.
        deadline = time.monotonic() + 15        
        client.camera = get_first_connected_camera(client)
        device_name = client.camera.getDeviceName()

        if client.camera is None:
            devices = [
                d.getDeviceName() for d in client.getDevices()
            ]
            raise RuntimeError(
                f"Camera {device_name!r} not found. "
                f"Available devices: {devices}"
            )

        print(f"Found camera: {device_name}")

        # Receive image data from this camera.
        # Options: B_NEVER, B_ALSO (Send BLOBs), B_ONLY
        client.setBLOBMode(PyIndi.B_ALSO, device_name, None)
        client.enableDirectBlobAccess(device_name, None)
        
        print("After BLOB settings")
        
        # Set the X and Y resolution for the camera
        client.getResolution();

        # Connect the camera if it is not already connected.
        connection = client.wait_for_property(
            client.camera, "CONNECTION"
        )

        if connection.getState() != PyIndi.IPS_OK:
            switches = camera.getSwitch("CONNECTION")
            if switches is None:
                raise RuntimeError(
                    "Camera has no CONNECTION switch property"
                )

            for switch in switches:
                switch.setState(PyIndi.ISS_OFF)

            connect_switch = switches.findWidgetByName("CONNECT")
            if connect_switch is None:
                raise RuntimeError(
                    "Cannot find CONNECT switch on camera"
                )

            connect_switch.setState(PyIndi.ISS_ON)
            client.sendNewSwitch(switches)

        # Wait for the camera connection to complete.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if connection.getState() == PyIndi.IPS_OK:
                break
            if connection.getState() == PyIndi.IPS_ALERT:
                raise RuntimeError("Camera connection failed")
            time.sleep(0.1)
        else:
            raise TimeoutError("Camera connection timed out")

        print("Camera connected.")

        # Wait for the exposure control to become available.
        client.wait_for_property(client.camera, "CCD_EXPOSURE")

        exposure = client.camera.getNumber("CCD_EXPOSURE")
        if exposure is None or len(exposure) == 0:
            raise RuntimeError("CCD_EXPOSURE property unavailable")

        # Set a one-second exposure.
        exposure[0].setValue(0.0001)

        # Start the exposure.
        print("Taking a 1-second exposure...")
        client.sendNewNumber(exposure)

        # Wait for the image BLOB, allowing extra download time.
        if not client.image_received.wait(timeout=90):
            raise TimeoutError(
                "No image received within 90 seconds"
            )

        if client.image_error:
            raise RuntimeError(
                f"Could not save image: {client.image_error}"
            )

        if client.image_path is None:
            raise RuntimeError("No image data was saved")

        print("Capture completed successfully.")

    finally:
        if client.isServerConnected():
            client.disconnectServer()

# define a method to test the module
def main():

    try:
        indiClient = IndiCameraClient()
        indiClient.connectToIndiServer()
        if indiClient.isIndiConnected:
            print("Connected to Indi server", indiClient.indiHost, indiClient.indiPort)
        else:
            print("Unable to connect to indi server", indiClient.indiHost, indiClient.indiPort)
        
        indiClient.connectCamera()
        if indiClient.isCameraConnected:
            print("Camera is ", indiClient.indiCameraName)
        else:
            print("No camera found")
        
        indiClient.setExposure(0.01)
        indiClient.get_frame()
        #print(f"Pre convert {indiClient.indiClient.output_file}")
        #indiClient.convertFitsToJpeg()
        indiClient.disconnectFromIndiServer()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
