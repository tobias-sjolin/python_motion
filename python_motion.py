#!/usr/bin/python

# original script by brainflakes, improved by pageauc, peewee2 and Kesthal
# www.raspberrypi.org/phpBB3/viewtopic.php?f=43&t=45235

# You need to install PIL to run this script
# type "sudo apt-get install python-imaging-tk" in an terminal window to do this

import StringIO
import subprocess
import os
import time
import commands
import smtplib, os, sys
import ftplib
from datetime import datetime
from PIL import Image
from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email.Utils import COMMASPACE, formatdate
from email import Encoders

# Motion detection settings:
# Threshold          - how much a pixel has to change by to be marked as "changed"
# Sensitivity        - how many changed pixels before capturing an image, needs to be higher if noisy view
# ForceCapture       - whether to force an image to be captured every forceCaptureTime seconds, values True or False
# filepath           - location of folder to save photos
# filenamePrefix     - string that prefixes the file name for easier identification of files.
# diskSpaceToReserve - Delete oldest images to avoid filling disk. How much byte to keep free on disk.
# cameraSettings     - "" = no extra settings; "-hf" = Set horizontal flip of image; "-vf" = Set vertical flip; "-hf -vf" = both horizontal and vertical flip
# ongoingTime        - Defining an ongoing event rather than a new event. If a motion occurs within this time is is defined as part of the last motion
# ongoingTimeCheck   - Defining a long ongoing event. If longer than this time then we want to do more.
threshold = 10
sensitivity = 20
forceCapture = False
forceCaptureTime = 60 * 60 # Once an hour
filepath = "/home/pi/python_motion"
filenamePrefix = "capture"
diskSpaceToReserve = 400 * 1024 * 1024 # Keep 400 mb free on disk
cameraSettings = ""
ongoingTime = 1 * 60 # One minute
ongoingTimeCheck = 5*60 # Five minutes

# settings of the photos to save
saveWidth   = 1296
saveHeight  = 972
saveQuality = 15 # Set jpeg quality (0 to 100)

# Test-Image settings
testWidth = 100
testHeight = 75

# this is the default setting, if the whole image should be scanned for changed pixel
testAreaCount = 1
testBorders = [ [[1,testWidth],[1,testHeight]] ]  # [ [[start pixel on left side,end pixel on right side],[start pixel on top side,stop pixel on bottom side]] ]
# testBorders are NOT zero-based, the first pixel is 1 and the last pixel is testWith or testHeight

# with "testBorders", you can define areas, where the script should scan for changed pixel
# for example, if your picture looks like this:
#
#     ....XXXX
#     ........
#     ........
#
# "." is a street or a house, "X" are trees which move arround like crazy when the wind is blowing
# because of the wind in the trees, there will be taken photos all the time. to prevent this, your setting might look like this:

# testAreaCount = 2
# testBorders = [ [[1,50],[1,75]], [[51,100],[26,75]] ] # area y=1 to 25 not scanned in x=51 to 100

# even more complex example
# testAreaCount = 4
# testBorders = [ [[1,39],[1,75]], [[40,67],[43,75]], [[68,85],[48,75]], [[86,100],[41,75]] ]

# in debug mode, a file debug.bmp is written to disk with marked changed pixel an with marked border of scan-area
# debug mode should only be turned on while testing the parameters above
debugMode = False # False or True

# Capture a small test image (for motion detection)
def captureTestImage(settings, width, height):
    command = "raspistill %s -w %s -h %s -t 200 -e bmp -n -o -" % (settings, width, height)
    imageData = StringIO.StringIO()
    imageData.write(subprocess.check_output(command, shell=True))
    imageData.seek(0)
    im = Image.open(imageData)
    buffer = im.load()
    imageData.close()
    return im, buffer

# Save a full size image to disk
def saveImage(settings, width, height, quality, diskSpaceToReserve, ongoing):
    keepDiskSpaceFree(diskSpaceToReserve)
    time = datetime.now()
    day = datetime.today().strftime("%Y%m%d")
    #Capture image
    filename = filenamePrefix + "-%04d%02d%02d-%02d%02d%02d.jpg" % (time.year, time.month, time.day, time.hour, time.minute, time.second)
    subprocess.call("raspistill %s -w %s -h %s -t 200 -e jpg -q %s -n -o %s" % (settings, width, height, quality, filepath + "/" +filename), shell=True)
    ftp_file(day,filepath,filename)
    print "Captured image: %s" % (filename)
    if ongoing == 2:
        #If we have an ongoing movement then we do not want to send spam. It is sufficient to get emails about new movements.
        #Also we don't do video
        print "Motion going on but not that weird so we do nothing for now"
    elif ongoing == 1:
        #Send image to email
        send_mail(sys.argv[1], [sys.argv[2]], 'Motion detected!', 'Image:', [filepath +"/"+filename],sys.argv[3])
        #Capture 5 sec video
        filename_vid = filenamePrefix + "-%04d%02d%02d-%02d%02d%02d.h264" % (time.year, time.month, time.day, time.hour, time.minute, time.second)
        subprocess.call("raspivid -n -o %s" % (filepath + "/" + filename_vid), shell=True)
        #FTP video
        ftp_file(day,filepath,filename_vid)
        print "Captured video: %s" % (filename_vid)
    elif ongoing == 3:
        #Send image to email
        send_mail(sys.argv[1], [sys.argv[2]], 'Motion still going on!', 'Image:', [filepath +"/"+filename],sys.argv[3])
        #Capture 5 sec video
        filename_vid = filenamePrefix + "-%04d%02d%02d-%02d%02d%02d.h264" % (time.year, time.month, time.day, time.hour, time.minute, time.second)
        subprocess.call("raspivid -n -o %s" % (filepath + "/" + filename_vid), shell=True)
        #FTP video
        ftp_file(day,filepath,filename_vid)
        print "Captured video: %s" % (filename_vid)
    else: 
        print "Not supported"
    print "Done"    

# Keep free space above given level
def keepDiskSpaceFree(bytesToReserve):
    if (getFreeSpace() < bytesToReserve):
        for filename in sorted(os.listdir(filepath + "/")):
            if filename.startswith(filenamePrefix) and filename.endswith(".jpg"):
                os.remove(filepath + "/" + filename)
                print "Deleted %s/%s to avoid filling disk" % (filepath,filename)
                if (getFreeSpace() > bytesToReserve):
                    return

def ftp_file(directory,filepath,filename):
    try:
        session = ftplib.FTP(sys.argv[4],sys.argv[5],sys.argv[6])
        file = open(filepath + "/" + filename,'rb')                  # file to send
        #Change to Motion directory
        try:
            session.cwd("PythonMotion")
        except Exception, e:
            if "PythonMotion" in str(e):
                session.mkd("PythonMotion")
                session.cwd("PythonMotion")
                print "Did not find PythonMotion folder. Created it"
        #Change to daily directory
        try:
            session.cwd(directory)
        except Exception, e:
            if directory in str(e):
               session.mkd(directory)
               session.cwd(directory)
               print "Did not find " + directory + " folder. Created it"
        session.storbinary('STOR ' + filename, file)     # send the file
        file.close()                                    # close file and FTP
        session.quit()
    except Exception, e:
        print str(e)

def send_mail(send_from, send_to, subject, text, files=[], server="localhost"):
    assert type(send_to)==list
    assert type(files)==list

    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach( MIMEText(text) )

    for f in files:
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(f,"rb").read() )
        Encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(f))
        msg.attach(part)

    smtp = smtplib.SMTP(server)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()

# Get available disk space
def getFreeSpace():
    st = os.statvfs(filepath + "/")
    du = st.f_bavail * st.f_frsize
    return du

#Print out config options
print "Mail address From: " + sys.argv[1] 
print "Mail address To: " + sys.argv[2] 
print "Mail server: " + sys.argv[3] 
print "Ftp server: " + sys.argv[4]
print "Ftp user: " +sys.argv[5]
print "Ftp pwd: " +sys.argv[6]

# Get first image
image1, buffer1 = captureTestImage(cameraSettings, testWidth, testHeight)

# Reset last capture time
lastCapture = 0

while (True):

    # Get comparison image
    image2, buffer2 = captureTestImage(cameraSettings, testWidth, testHeight)

    # Count changed pixels
    changedPixels = 0
    takePicture = False
    ongoing = 1 #Variable to detect if it is an ongoing motion (2), new motion (1) or long ongoing motion (3)

    if (debugMode): # in debug mode, save a bitmap-file with marked changed pixels and with visible testarea-borders
        debugimage = Image.new("RGB",(testWidth, testHeight))
        debugim = debugimage.load()

    for z in xrange(0, testAreaCount): # = xrange(0,1) with default-values = z will only have the value of 0 = only one scan-area = whole picture
        for x in xrange(testBorders[z][0][0]-1, testBorders[z][0][1]): # = xrange(0,100) with default-values
            for y in xrange(testBorders[z][1][0]-1, testBorders[z][1][1]):   # = xrange(0,75) with default-values; testBorders are NOT zero-based, buffer1[x,y] are zero-based (0,0 is top left of image, testWidth-1,testHeight-1 is botton right)
                if (debugMode):
                    debugim[x,y] = buffer2[x,y]
                    if ((x == testBorders[z][0][0]-1) or (x == testBorders[z][0][1]-1) or (y == testBorders[z][1][0]-1) or (y == testBorders[z][1][1]-1)):
                        # print "Border %s %s" % (x,y)
                        debugim[x,y] = (0, 0, 255) # in debug mode, mark all border pixel to blue
                # Just check green channel as it's the highest quality channel
                pixdiff = abs(buffer1[x,y][1] - buffer2[x,y][1])
                if pixdiff > threshold:
                    changedPixels += 1
                    if (debugMode):
                        debugim[x,y] = (0, 255, 0) # in debug mode, mark all changed pixel to green
                # Save an image if pixels changed
                if (changedPixels > sensitivity):
                    takePicture = True # will shoot the photo later
                if ((debugMode == False) and (changedPixels > sensitivity)):
                    break  # break the y loop
            if ((debugMode == False) and (changedPixels > sensitivity)):
                break  # break the x loop
        if ((debugMode == False) and (changedPixels > sensitivity)):
            break  # break the z loop

    if (debugMode):
        debugimage.save(filepath + "/debug.bmp") # save debug image as bmp
        print "debug.bmp saved, %s changed pixel" % changedPixels
    # else:
    #     print "%s changed pixel" % changedPixels

    # Check force capture
    if forceCapture:
        if time.time() - lastCapture > forceCaptureTime:
            takePicture = True
            print "Because of force, no movement"

    if takePicture:
        #If lastcapture was within ongoingTime then we classify this as an ongoing movement
        secondsSinceLast = time.time() -lastCapture
        if secondsSinceLast < ongoingTime:
            ongoing = 2            
            print "Ongoing movement since number of seconds since last movement was " + str(secondsSinceLast) + ". This event started " + str(time.time() - ongoingStarted) + " seconds ago."
            #However if this has been an ongoing thing for longer than ongoingTimeCheck then we want to do a new check with this knowledge
            if time.time() - ongoingStarted > ongoingTimeCheck:
                ongoing = 3
                ongoingStarted = time.time() #And we do this to reset the ongoing event so we do not get spammed after this.
                print "Still ongoing but we really want to check what is up"
        else:
            ongoingStarted = time.time()
            print "New movement" 
        lastCapture = time.time()
        saveImage(cameraSettings, saveWidth, saveHeight, saveQuality, diskSpaceToReserve, ongoing)

    # Swap comparison buffers
    image1 = image2
    buffer1 = buffer2
