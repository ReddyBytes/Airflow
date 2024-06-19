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
1) [Airflow installation Guide](/Airflow_Installation/Installation_Guide.md)  
2) [Postgres connection to airflow](/DAGS/Postgres_Operator/Notes.md)  
3) [S3 connection to Airflow]()  
4) [S3 Sensors](/DAGS/S3_Operator/S3_Sensors.py)  

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

----
---
### How airflow works
![](https://media.licdn.com/dms/image/D5622AQE7hiWDSNzBHw/feedshare-shrink_2048_1536/0/1705147535482?e=2147483647&v=beta&t=Sq-s_24Iv5r4mtYj6-j1eYKIswfN6NJ5TR6zlx5XS2c)



### Limitations :  

we cant use airflow as `Streaming` and `data processing tool`


# core concepts

## DAG (Directed Acyclic Graph)

- A DAG (Directed Acyclic Graph) is a collection of tasks organized by their dependencies and relationships, defining how they should run.  
-  DAGs are written in Python and placed in Airflow's designated folder, allowing for dynamic building and execution of workflows.  
- simply DAG is a data pipeline

![](https://www.steveclarkapps.com/wp-content/uploads/2019/03/DirectGraphs_CyclicAcyclic.jpg)  

## Operators
- simply operator is a Task 
- it encapsulates the logic that we are going to perform  

### 1) Action Operators

Action operators are used to perform actions such as executing shell commands, calling external services, or manipulating data.

- **PythonOperator**: Executes a Python callable.
- **BashOperator**: Executes a bash command.
- **ShellOperator**: Executes a shell command.
- **EmailOperator**: Sends an email notification.
- **SlackOperator**: Posts a message to Slack.
- **SnsPublisher**: Publishes a message to AWS Simple Notification Service (SNS).
- **PostgresOperator**: Executes a postgresql ,sql queries
- **MySQLOperator**: Executes SQL statements against a MySQL database.
- **SnowflakeOperator**: Executes SQL statements against a Snowflake database.

### 2) Transfer Operators

Transfer operators are specifically designed for moving data between locations. 

- **CopyToS3Operator**: Copies files to Amazon S3.
- **MoveFileOperator**: Moves a file from one location to another.
- **SFTPOperator**: Transfers files via SFTP.
- **GoogleCloudStorageToBigQueryOperator**: Loads data from Google Cloud Storage into BigQuery.
- **HdfsToS3Operator**: Copies files from HDFS to Amazon S3.



### 3) Sensor Operators

Sensor operators wait for a condition to become true before proceeding with the next task.

- **HttpSensor**: Waits until a given URL returns a successful HTTP response for every 60sec.
- **FileSensor**:it checks whether the file exists or not in the file system for every 10 sec
- **SqlSensor**: Waits until a SQL query returns a result.
- **GCSObjectExistenceSensor**: Checks if a Google Cloud Storage object exists.

---
### a) External System Interaction Operators

- **HttpOperator**: Makes an HTTP request.
- **RestApiOperator**: Calls a REST API endpoint.
- **KafkaConsumerOperator**: Consumes messages from a Kafka topic.
- **KafkaProducerOperator**: Produces messages to a Kafka topic.

### b) Utility Operators

- **DummyOperator**: Does nothing and is used for testing.
- **BranchPythonOperator**: Branches the workflow based on the return value of a Python callable.
- **TriggerRule**: Defines the trigger rule for a task, specifying when it should be executed.



