# What is Amazon EKS?

Amazon Elastic Kubernetes Service (EKS) is a managed service that makes it easy to run Kubernetes on AWS without needing to install, operate, and maintain your own Kubernetes control plane.

## Key Features

- **Managed Kubernetes Service**: EKS takes care of the underlying Kubernetes infrastructure, allowing you to focus on deploying and managing applications.

- **Highly Available and Secure**: EKS clusters are highly available and secure, automatically scaling compute resources and integrating with AWS security features.

- **Integration with AWS Services**: Seamlessly integrate with other AWS services like Amazon RDS, Amazon S3, and AWS IAM for a cohesive cloud experience.

- **Familiar Kubernetes Experience**: Use familiar Kubernetes tooling and workflows, including `kubectl`, Helm charts, and CI/CD pipelines.



## Managing EKS Clusters

![](https://aws.github.io/aws-eks-best-practices/networking/subnets/image.png)

ENI ----> Elastic Network Interface

To know more about IPv4/IPv6 [click here](https://github.com/ReddyBytes/AWS---Amazon-Web-Services/blob/main/1-IP_address.md)

- EKS clusters consist of control plane instances running Kubernetes software and worker nodes running in your AWS account. 
- The control plane is provisioned across multiple Availability Zones and fronted by an Elastic Load Balancing, Network Load Balancer. 
- Nodes connect to the control plane over the Kubernetes API server endpoint and a certificate file created for your cluster.


## Setup AIRFLOW on AWS-EKS :

## 1. create EC2 instance
__Step 1 :__ Launch Ec2 instance with  below details  
  
    AMI           : Linux prefered

    Instance type : Memory > 2 GiB  ex : t2.small

    VPC           : default

    Key pair      : create new key pair

    Add security groups : SSH:22 HTTP:80, HTTPS:443  protocol=TCP

    storage configuration : default

    Launch instance

__Step 2 :__ Connect to the instance on AWS browser 

    click on connect >> select "connect ec2 instance through ssh on browser" >> choose username ( ec2-user)

__Step 3 :__ command to use
  
    sudo yum update -y

    sudo amazon-linux-extras install docker

    sudo service docker start

    sudo usermod -a -G docker ec2-user

    

__Step 4 :__ logout and again login to the instance

__Step 5 :__ run the rancher container
  
    docker run -d --restart=unless--stapped --name rancher --hostname rancher -p 80:80 -p 443:443 rancher

    docker ps
   
__Step 6 :__ connect to the rancher by using your public ip


__Step 7 :__ set password and done you can see like 

then we need to create an user using IAM as below


## 2.  Setup user using IAM
__Step 1 :__ go to IAM service >> users >> add user
  
    name : airflow-user

    password : select as per usr requirements

    permissions : you can create new permissions or existing policies

`Download the csv file which contains ccess key credentials bz we can't see those in future`

## 3. Create ECR registry

### What is ECR ?

- Amazon Elastic Container Registry (ECR) is a fully-managed Docker container registry service provided by Amazon Web Services (AWS). 

- It allows users to store, manage, and deploy Docker container images securely. 
- similar to dockerhub

- we can control access to our Docker images using AWS Identity and Access Management (IAM) policies like who can pull and push images to your repository.

- ECR integrates seamlessly with AWS CodeBuild, AWS CodePipeline, and other CI/CD tools. This enables automated workflows for building, testing, and deploying applications.

### creating ECR Registry 

__Step 1 :__ Login AWS >> ECR service >> create a repositary
  
    i. choose private / public
    ii. give name <namespace>/<repositary-name>
    iii. save & create repo

__Step 2 :__ Install AWS CLI to push images to ECR
  
open the [link](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) choose the os and follow the instructions .  
Here i choose linux as my OS

    sudo yum remove awscli

    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip awscliv2.zip
    sudo ./aws/install 

    aws --version

    aws configure

    # provide your Access key and ssecret key that you downloaded in IAM step 1 

    # if u want to give region u can give or keep default by "click  enter"

    # use the 1st push command from the ECR >> select repo >> view push commands

    # to build image ,tag, push follow the push commands in ECR as seen in below


![](https://miro.medium.com/v2/resize:fit:2000/1*_7h8Whez0VWCTituZ71MFQ.png)

## 4. Create EKS cluster using Rancher

__Step 1 :__ Go to the rancher site created in  >> add/create cluster >> select AWS EKS

![](https://miro.medium.com/v2/resize:fit:1400/1*2RW73wHLLIrJomviJLgnTw.png)

__Step 2 :__ Give the details
  
    cluster name  : your_cluster_name

    aws_region : as ur aws console region 

    aws-Access key : you can find in csv file
    aws -Secret-key : you can find in csv file

    k8s-version : choose appropriate version 

    # remaining all parameters keep it as default

    create  ---> it takes 2 to 5 min to setup cluster depends on system

__Step 3 :__ now you can see that cluster in EKS service 

__Step 4 :__ you can use kubectl from rancher itself


### 5. Deploy nginx 

__Step 1 :__ enable catalogs from rancher >>global view >> apps >> catalogs >> enable helm 