__step 1  :__ up the docker compose yaml file.  
__step 2 :__ after running the container login to airflow webserver ( 8080 ) and flower ui ( 5555 )  


## How to add new worker
Step 1 : 
  
    docker run -d --network <your_docker_compose_network> -v <absolute_path__for_dags_folder>:<_path_to_ur_container_folder> -v <absolute_path__for_airflow.cfg file>:<_path_to_ur_container_folder> <image name>

    docker run -d my_network -v ./mnt/airflow/dags:/usr/local/airflow -v ./mnt/airflow/airflow.cfg:/usr/local/airflow/airflow.cfg python:3.9

Step 2 : exec into the created container
  
    docker exec -it <container_id> /bin/bash

Step 3 : export the container path
  
    export AIRFLOW_HOME=/usr/local/airflow

Step 4: add user 
  
    useradd -ms /bin/bash -d $AIRFLOW_HOME airflow
Step 5 : install the apache in container
  
    pip install "apache_airflow[celery, crypto, postgres, redis]=2.4.0"

Step 6 : initializt the database 
  
    airflow initdb

Step 7 : change the permisiions ti airflow home
  
    chown -R airflow: $AIRFLOW_HOME

Step 8 : login to airflow user
  
    su - airflow 

    ls  # you can find the logs, .cfg, db files 

Step 9 : make some changes in airflow.cfg file
  
    1) sql_alchemy_conn = postgresql+psycopg2://airflow:airflow@postgres:5432/airflow

    2) executor = CeleryExecutor

    3) result_backend = db+postgresql://airflow:airflow@postgres:5432/airflow

    4) broker_url = redis://:redispass@redis:6379/1

Step 10 : save the cfg file and in terminal run export command again

Step 11 : 
  
    airflow worker

Step 12 : check the worker in flower browser

`To scale more workers use command`  
  
    docker compose -f <docker_compose_file_name> scale worker=3 

it will scale to 4 worker nodes 


--- 
---

### How to send a task to particular worker 

Step 1 : For this 1st we need to define names to workers and add in docker compose file >> services >> worker >> commands ====> as below
   
     command: worker -q worker_1,worker_2,worker_3

Step 2 : if worker r running then ok if not do Step 12

Step 3 : check the worker names in flower ui >> go to any worker >> queues  

Step 4 : trigger the queue_dag.py file dag

Step 5 : may be no task is running in flower ui because we didn't add default in docker compose file like below 
  
    command: worker -q worker_1,worker_2,worker_3,default 

because check airflow.cfg file default_queue = default 

Step 6 : add queue parameter in queue_dag file like in queue_dag_2.py file


    