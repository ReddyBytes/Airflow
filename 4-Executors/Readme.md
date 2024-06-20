## Executors 

- Executors are the mechanisms responsible for executing task instances. 
- They play a crucial role in determining how tasks are run, whether locally on the same machine as the scheduler or remotely on separate machines. 
- Executors come with various configurations and capabilities, catering to different use cases ranging from development to production environments.


### Types of Executors

#### 1) SequentialExecutor

- **Description**:  
    - The default executor in Airflow, designed for simplicity and ease of use during development and testing. It executes tasks sequentially, one at a time.

- **Use Case**: 
    - Best suited for `debugging` and `development` due to its simplicity. 
    - <u>Not recommended for production environments </u> due to its lack of parallelism and susceptibility to single-point failures.

- **Database Compatibility**: 
    - Compatible with SQLite, making it suitable for setups where multiple connections are not supported.
    - SQLite is limit upto 140TB
    - Database stored in a single disk file

![](https://miro.medium.com/v2/resize:fit:1400/1*xLKIM-wldyYfPGGgdxIcDA.png)

#### 2) LocalExecutor

- **Description**: 
    - Executes tasks on the same machine as the scheduler, allowing for parallel execution of tasks. 
    - Vertical Scaling
    - single point of failure


- **Use Case**: 
    -  Ideal for small production environments where tasks can be efficiently run on the same machine as the scheduler.  
    - Requires a database that supports multiple connections, such as MySQL or PostgreSQL.

- **Parallelism**: 
    - `Parallelism :` The maximum number of task instances that can run simultaneously across all DAGs.
    - `max_active_tasks_per_dag :` The maximum number of task instances that can run concurrently for a single DAG.
    

#### 3) CeleryExecutor

Celery is a powerful tool for handling asynchronous tasks in Python and beyond. Its flexibility, scalability, and robustness make it suitable for a wide range of applications, from web scraping to data processing pipelines.

- **Description**: 
    - Utilizes Celery as a distributed task queue to execute tasks asynchronously. 
    - It integrates with Celery workers, allowing tasks to be distributed across multiple worker nodes.

- **Use Case**: 
    - suitable for medium to large-scale production environments.
    - Best for production environments requiring high levels of concurrency and scalability. 

- **Parallelism**: 
 
    - Achieves high levels of parallelism by distributing tasks among a pool of Celery workers, supporting dynamic scaling based on workload demands.

    ![](https://miro.medium.com/v2/resize:fit:1400/1*dlQpAZ4S3UYxpM-U2E7ihw.png)

    ![](https://miro.medium.com/v2/resize:fit:2000/1*avBjYUY6ZtfEyTkk7FI8JQ.png)

     __Flower :__  is a webserver to manage the celery worker nodes etc., runs on port 5555
     ![](https://tests4geeks.com/blog/wp-content/uploads/2016/04/celery-flower.gif) 

#### 4) KubernetesExecutor

- **Description**: 
    - Executes tasks within Kubernetes pods, taking advantage of Kubernetes' orchestration capabilities. 

- **Use Case**: 
    - suitable for cloud-native applications and microservices architectures.
    - Suitable for production environments running on Kubernetes, offering seamless integration with Kubernetes' scheduling and orchestration features.

- **Parallelism**: 
    - Leverages Kubernetes scheduling capabilities to distribute tasks across a cluster of nodes, achieving high levels of parallelism and scalability.

#### 5) Custom Executors

Airflow allows for the creation of custom executors by implementing the `BaseExecutor` interface. This capability enables the development of executors tailored to specific use cases, integrating with proprietary tools, services, or cloud providers.
