## Automated Student Attendance with AWS-powered Image Recognition

## About

This project was carried out by a team of two students as a component of the CSE 546 course. It features a three-tier architecture, comprising the web-tier, app-tier, and data-tier, and utilizes AWS resources for scaling both up and down in response to changing workloads.

Overview:

Web Tier
The uploaded image is received by a web-tier HTTP server, which runs on a t2.micro EC2 instance, utilizing a Flask application server due to its strong compatibility with AWS through the use of boto3 for instance management. The server processes incoming images and places them into the request queue within SQS, including both the image's name and ID

The app tier initiates with a single t2.micro EC2 instance launched from the provided AMI containing the deep-learning model used for image label prediction. This instance is equipped with a Python script named classify.py. 

The data tier consists of S3 buckets to store the input images and the classified results.

## Getting Started

For web-tier :

• Connect to web-tier instance using ubuntu as user.
• Install the required python libraries:
o Flask
o Threading
o Time
o Boto3
o Subprocess
o os 
• python3 cc_server.py


For app-tier : 

• Connect to web-tier instance using ubuntu as user.
• Install the required python libraries:
o Flask
o Threading
o Time
o Boto3
o Subprocess
o os 
• python3 classify.py



