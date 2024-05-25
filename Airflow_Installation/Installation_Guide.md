# Install Airflow using Docker compose  
__Step 1 :__   Install docker in your instance as root user . here i take ubuntu as my machine
  
     sudo su -
     curl -fsSL https://get.docker.com -o get-docker.sh
     sudo sh get-docker.sh


__Step 2 :__ make a directory for airflow in /opt folder. And enter into the folder 
  
    mkdir /opt/airflow  
    cd /opt/airflow 

__Step 3 :__ Copy the docker compose file to the current directory. You can find the docker compose .yml file in this folder itself.   
This compose file is with LocalExecutor  
  
    curl -LfO ''


__Step 4 :__ Setup the necessary parent directories and user permissions to create DAGS in the current directory.
  
    mkdir -p ./dags ./logs ./plugins ./config
    echo -e "AIRFLOW_UID=$(id -u)" > .env  


__Step 5 :__ Now run docker compose file with airflow installation.  
  
    docker compose up airflow-init

__Step 6 :__ at last up the docker compose file.  
  
    docker compose up -d   

__Step 7 :__ now checck the containers whether those are in running state or not.  
  
    docker ps  

![you can see like this ](https://cdn.hashnode.com/res/hashnode/image/upload/v1683476464772/5feb9436-2f59-4473-a86e-52b7397c3012.png?auto=compress,format&format=webp)  

__Step 8 :__ Here if the webserver is in running state the you cal login to the browser.  
  
    http://localhost:8080/  

![](https://cdn.hashnode.com/res/hashnode/image/upload/v1683476697940/7c835382-1272-4d74-8238-be375867e46a.png?auto=compress,format&format=webp) 


__Step 9 :__ username and password are the same present in the docker compose.yml file in service section under posrgres u can find username and password.  
