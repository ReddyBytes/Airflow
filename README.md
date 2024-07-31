
## learn below topics from this Repo:  
1) [Why we need airflow](/README.md#why-we-use-airflow)
2) [usecases of airflow](/README.md#use-cases)
3) [Architecture & core components](/README.md#architecture-of-airflow)  
        a) [webserver](/README.md#web-server)  
        b) [Metadata](/README.md#databasemetadata)  
        c) [Scheduler](/README.md#scheduler)  
        d) [Executor](/README.md#executor)  
        e) [Worker](/README.md#worker)  
        f) [Triggerer](/README.md#triggerer)  
4) [core concepts](/README.md#core-concepts)  
        a) [DAGS](/README.md#dag-directed-acyclic-graph)  
        b) [operators](/README.md#operators)
4) [How airflow works and limitations](/README.md#how-airflow-works)
1) [Airflow installation Guide](/1-Airflow_Installation/Installation_Guide.md)  
2) [Postgres Operator to airflow](/2-DAGS-&-Operators/Postgres_Operator/Readme.md)  
3) [S3 Operator to Airflow](/2-DAGS-&-Operators/S3_Operator/)  
4) [Sensors](/3-Sensors/)  

# Why We Use Airflow

Apache Airflow is a platform designed to programmatically author, schedule, and monitor workflows. It allows users to define complex computational workflows using Python and manage them through its web-based UI.   
The reasons why organizations choose to use Airflow:

### Scalability
- **Large Scale**: Airflow can handle large-scale workflows across distributed systems, making it suitable for big data processing pipelines.

### Flexibility
- **Python-Based**: Being based on Python, Airflow offers great flexibility in defining workflows, allowing for dynamic task dependencies and custom logic.

### Extensibility
- **Plugin Architecture**: Airflow supports plugins, enabling users to extend its functionality according to their needs.

### Monitoring and Troubleshooting
- **Web UI**: Provides a comprehensive dashboard for monitoring workflow runs, including detailed logs and error messages.
- **Error Handling**: Offers robust mechanisms for handling errors and retries, improving reliability.

### Dynamic Task Dependencies
- **DAGs (Directed Acyclic Graphs)**: Allows for the definition of complex workflows where tasks have dependencies on each other, ensuring that tasks run in the correct order.

### Integration Capabilities
- **Wide Range of Integrations**: Supports integration with various data storage systems, cloud providers, and third-party APIs, facilitating seamless data processing workflows.

### Orchestration
- **Workflow Management**: Manages the orchestration of complex computational workflows, automating the process of scheduling and executing tasks.

## Use Cases

- **Data Pipeline Automation**: Automating data extraction, transformation, and loading (ETL) processes.

- **Machine Learning Pipelines**: Managing machine learning workflows, from data preprocessing to model training and deployment.

- **Continuous Integration/Continuous Deployment (CI/CD)**: Orchestrating CI/CD pipelines, automating software builds, tests, and deployments.

- **Batch Processing**: Scheduling batch jobs for processing large volumes of data.



# Architecture of Airflow 

![](https://miro.medium.com/v2/resize:fit:1400/1*PWQB6lj12818Kzp-rszvpw.png)  


![](https://coder2j.com/img/airflow/task-life-cycle-architecture/airlfow-task-retry-and-reschedule.png)
### Core Components

### Web Server
- **Functionality**: Provides a user interface for interacting with Airflow, allowing users to monitor task execution, view the status of DAGs, and access logs and other operational information.

### Database/Metadata
- **Functionality**: Stores all DAG and task metadata. Typically a Postgres database, but MySQL and SQLite are also supported.
- **Role**: Ensures persistence and recovery from failures, serving as a central repository for managing and monitoring task execution.

### Scheduler
- **Functionality**: Responsible for scheduling jobs. It scans the DAGs directory to determine what tasks need to be run, when they need to be run, and where they are run.
- **Interaction**: Interacts with the metadata database to store and retrieve task state and execution information.  

### Executor
- **Functionality**: Executes tasks. It is a configuration property of the scheduler and runs within the scheduler process.
- **Types**: Includes Sequential Executor, LocalExecutor, CeleryExecutor, and KubernetesExecutor etc.


### Worker
- **Functionality**: Executes tasks as defined by the executor. The presence of workers depends on the chosen executor type.

### Triggerer
- **Functionality**: Supports deferrable operators. This component is optional and must be run separately, needed only for using deferrable operators.


### Limitations :  

we cant use airflow as `Streaming` and `data processing tool`

----
----

## Single Node vs. Multi-Node Architecture


### 1) Single-Node Architecture

- In a single-node architecture, all components of Airflow reside on a single machine. 
- This setup is straightforward and requires minimal configuration, making it suitable for small-scale deployments or environments with moderate amounts of DAGs.


![](https://miro.medium.com/v2/resize:fit:1400/1*xLKIM-wldyYfPGGgdxIcDA.png)

#### Components:

- **Webserver**: Handles HTTP requests and serves the Airflow UI, allowing users to interact with their workflows.

- **Scheduler**: Monitors the metadata database for new tasks and schedules them for execution.

- **Worker (LocalExecutor)**: Executes tasks locally on the same machine. It pulls tasks from an IPC (Inter Process Communication) queue and runs them.

#### Advantages:

- Simplicity: Easy to set up and manage.
- No external dependencies required.

#### Limitations:

- Scalability: Difficult to scale beyond the capabilities of a single machine.
- Performance: May become a bottleneck as the workload increases.

### 2) Multi-Node Architecture

- A multi-node architecture distributes Airflow components across multiple machines, enhancing scalability, reliability, and performance. 
- This setup is ideal for larger, more complex workflows and environments that require high availability and the ability to scale horizontally.

![](https://miro.medium.com/v2/resize:fit:1400/1*7pr0Q1zV1d29E5pt87Xmag.png)
#### Components:

- **Webserver & Scheduler**: Typically co-located on one machine for simplicity, though they can be distributed.

- **Workers (CeleryExecutor)**: Run on separate machines, executing tasks concurrently. Workers communicate with each other and the scheduler through a message queue (e.g., Redis).

#### Advantages:

- **Scalability**: Easily scale up by adding more workers.

- **High Availability**: If one worker node fails, others continue operating.
- **Resource Optimization**: Dedicated workers can be allocated for specific types of tasks, optimizing resource usage.

#### Limitations:

- Complexity: More challenging to set up and manage due to distributed nature.
- Dependency on external messaging systems (e.g., Redis, RabbitMQ).

## Workflow in Airflow

Airflow workflows are defined as Directed Acyclic Graphs (DAGs), where each node represents a task, and edges represent dependencies between tasks.

1. **Planning Phase**: The scheduler reads DAG definitions from the metadata database and plans the execution order of tasks based on their dependencies.

2. **Execution Phase**: Tasks are dispatched to workers for execution. In a single-node setup, the local worker executes tasks. In a multi-node setup, tasks are distributed among workers, potentially running on different machines.
3. **Monitoring Phase**: Throughout execution, the scheduler monitors task progress and updates the metadata database accordingly. The webserver provides a UI for users to monitor the status of their workflows.


![](https://media.licdn.com/dms/image/D5622AQE7hiWDSNzBHw/feedshare-shrink_2048_1536/0/1705147535482?e=2147483647&v=beta&t=Sq-s_24Iv5r4mtYj6-j1eYKIswfN6NJ5TR6zlx5XS2c)
