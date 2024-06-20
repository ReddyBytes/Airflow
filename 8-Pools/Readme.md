## Airflow Pools : Managing Parallelism and Resources

#### Purpose of Pools

- **Limit Parallelism**: Pools restrict the number of tasks that can run in parallel, preventing overloading of shared resources.

- **Resource Management**: They help manage resource utilization, ensuring that tasks do not compete excessively for limited resources.

### Creating and Managing Pools


- **Via Airflow UI**: Navigate to Admin > Pools, and add a new pool by specifying its name, the number of slots (which determines the parallelism limit), and an optional description.

![](https://guptakumartanuj.wordpress.com/wp-content/uploads/2020/05/screen-shot-2020-05-09-at-4.28.52-pm.png)

- **Via Airflow CLI**: Use the `airflow pools set` command to create a new pool. Additionally, pools can be imported from a JSON file using the `import` subcommand for bulk pool definitions.

- **Via Airflow REST API**: Available in Airflow version 2.0 and later, pools can be created by submitting a POST request with the pool's name and number of slots as the payload.



### priority_weight
- task executes based on priority level/weight
- when we give priority_weight =1 then the task executes at 1st .
