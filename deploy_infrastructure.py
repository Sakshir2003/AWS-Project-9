import boto3
import json
import zipfile
import os
import time
import uuid

def create_lambda_deployment_package():
    print("Creating Lambda deployment package...")
    zip_path = 'lambda_function.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write('lambda_function.py')
    print(f"[OK] Deployment package {zip_path} created.")
    return zip_path

def deploy_serverless_image_resizer():
    region = 'ap-south-1' # Defaulting to ap-south-1 based on previous projects
    s3 = boto3.client('s3', region_name=region)
    iam = boto3.client('iam')
    lambda_client = boto3.client('lambda', region_name=region)
    
    # Generate unique suffix for globally unique S3 bucket names
    unique_id = str(uuid.uuid4())[:8]
    source_bucket = f"image-resizer-source-{unique_id}"
    dest_bucket = f"image-resizer-dest-{unique_id}"
    
    print(f"Deploying Serverless Image Resizer to region {region}...")
    
    # 1. Create S3 Buckets
    try:
        s3.create_bucket(
            Bucket=source_bucket,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
        print(f"[OK] Source bucket created: {source_bucket}")
    except Exception as e:
        print(f"Error creating source bucket: {e}")
        
    try:
        s3.create_bucket(
            Bucket=dest_bucket,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
        print(f"[OK] Destination bucket created: {dest_bucket}")
    except Exception as e:
        print(f"Error creating destination bucket: {e}")

    # 2. Create IAM Role for Lambda
    role_name = f"ImageResizerLambdaRole-{unique_id}"
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy)
        )
        role_arn = role['Role']['Arn']
        print(f"[OK] IAM Role created: {role_name}")
        
        # Attach basic execution role
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        
        # Create and attach S3 access policy
        s3_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": f"arn:aws:s3:::{source_bucket}/*"
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:PutObject"],
                    "Resource": f"arn:aws:s3:::{dest_bucket}/*"
                }
            ]
        }
        policy_response = iam.create_policy(
            PolicyName=f"ImageResizerS3Policy-{unique_id}",
            PolicyDocument=json.dumps(s3_policy)
        )
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn=policy_response['Policy']['Arn']
        )
        print("[OK] Attached S3 access policy to IAM Role.")
        
        print("Waiting for IAM role to propagate...")
        time.sleep(15) # Wait for role propagation
    except Exception as e:
        print(f"Error creating IAM Role: {e}")
        return

    # 3. Create Lambda Function
    zip_path = create_lambda_deployment_package()
    function_name = f"ImageResizerFunction-{unique_id}"
    
    try:
        with open(zip_path, 'rb') as f:
            zipped_code = f.read()
            
        # KLayers Public ARN for Pillow on ap-south-1 (Python 3.9)
        # Note: If this fails, user might need to package dependencies using Docker.
        layer_arn = "arn:aws:lambda:ap-south-1:770693421928:layer:Klayers-p39-pillow:1"
        
        lambda_response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime='python3.9',
            Role=role_arn,
            Handler='lambda_function.lambda_handler',
            Code={'ZipFile': zipped_code},
            Timeout=15,
            MemorySize=512,
            Environment={
                'Variables': {
                    'DESTINATION_BUCKET': dest_bucket
                }
            },
            Layers=[layer_arn] # Using Klayers for Pillow dependency
        )
        lambda_arn = lambda_response['FunctionArn']
        print(f"[OK] Lambda function created: {function_name}")
        
        # 4. Add Lambda Permission for S3 to invoke it
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId='S3InvokePermission',
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com',
            SourceArn=f"arn:aws:s3:::{source_bucket}"
        )
        print("[OK] S3 invoke permission added to Lambda.")
        
    except Exception as e:
        print(f"Error creating Lambda function: {e}")
        return

    # 5. Configure S3 Event Notification to trigger Lambda
    try:
        s3.put_bucket_notification_configuration(
            Bucket=source_bucket,
            NotificationConfiguration={
                'LambdaFunctionConfigurations': [
                    {
                        'LambdaFunctionArn': lambda_arn,
                        'Events': ['s3:ObjectCreated:*']
                    }
                ]
            }
        )
        print(f"[OK] S3 Event Notification configured on {source_bucket}.")
    except Exception as e:
        print(f"Error configuring S3 notification: {e}")

    print("\n" + "="*60)
    print("Deployment Successful!")
    print("Architecture Details:")
    print(f"- Source S3 Bucket:      {source_bucket}")
    print(f"- Destination S3 Bucket: {dest_bucket}")
    print(f"- Lambda Function:       {function_name}")
    print("="*60)
    print("To test the application:")
    print(f"1. Upload an image to the source bucket '{source_bucket}'.")
    print(f"2. Check the destination bucket '{dest_bucket}' for the resized image.")
    print("="*60)

if __name__ == "__main__":
    deploy_serverless_image_resizer()
