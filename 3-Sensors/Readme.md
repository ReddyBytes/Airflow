

## Sensor Operators

Sensor operators wait for a condition to become true before proceeding with the next task.

- **HttpSensor**: Waits until a given URL returns a successful HTTP response for every 60sec.
- **FileSensor**:it checks whether the file exists or not in the file system for every 10 sec
- **SqlSensor**: Waits until a SQL query returns a result.
- **GCSObjectExistenceSensor**: Checks if a Google Cloud Storage object exists.