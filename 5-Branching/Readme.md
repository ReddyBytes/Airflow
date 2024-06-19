## Branching

Branching allows dynamic routing of tasks based on the outcomes of preceding tasks. This capability is crucial for handling scenarios where the flow of operations depends on certain conditions being met.

### Example 1 : Cleaning Up Your Room where toys and clothes spread across the room

1. **Start**: You begin with deciding what to do first - pick up toys or sort clothes.
2. **Branching Decision**: Based on what you find first, you either call a function to pick up toys (`pick_toys`) or another function to sort clothes (`sort_clothes`). This decision is made dynamically, just like choosing your path in the game.
3. **Next Steps**: After picking up toys or sorting clothes, you move on to the next task, like vacuuming the floor.


### Example 2 : we can take user input of age :


![](https://airflow.apache.org/docs/apache-airflow/1.10.6/_images/branch_good.png)  