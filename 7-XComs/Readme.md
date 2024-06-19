# XComs --> Cross-Communication

XComs, enable tasks within a DAG to exchange small amounts of data. This mechanism is crucial for workflows where the output of one task serves as input for subsequent tasks.



XComs operate on a push-pull model:

- **Push Model**: A task pushes data to XComs, storing it in the Airflow database or a custom backend.
- **Pull Model**: Downstream tasks retrieve data from XComs, accessing it as needed.

### Benefits of Using XComs

- **Facilitates Data Sharing**: XComs simplify the sharing of data between tasks, supporting complex workflows that require data transformation or processing in stages.

- **Enables Dynamic Workflows**: They allow for dynamic construction of workflows, where the outcome of one task influences the next steps.

- **Improves Error Handling**: XComs can carry error messages or status codes, aiding in debugging and error handling across tasks.

### Limitations and Considerations

- **Data Size Restrictions**: There are limitations on the size of data that can be stored in XComs. For large datasets, alternative storage solutions like databases or cloud storage services are recommended.  

        XComs size depending on backend database  

        MySQL: 64 Kilobytes  
        SQLite: 2 Gigabytes  
        PostgreSQL: 1 Gigabyte   

- **Performance Implications**: Frequent data exchanges through XComs can affect the performance of your Airflow instances, especially in workflows with numerous tasks or large volumes of data.



![](https://miro.medium.com/v2/resize:fit:1400/1*yhq_n9iFAN8vqE78CHo_zA.png)

