# postgres connection with webserver  
 __Step : 1__ Go to webserver page > admin > connections  

![](https://lh5.googleusercontent.com/H5RVZ2yZnxvK8j_3RYHOydb04ICXulQy2zYT9NFM7qSFJFoYZ5sa8d3lOR9v5A0AIp9rxKGVES_KL16LcgN-b2_tgOD1ULl3h3QcHVVospJH9fGI4V6ymNxoEceYH9dMqlrs-Xfs)  

 __Step : 2__ Tap on " + " to add new connection  

 ![](https://s3.amazonaws.com/recipes.dezyre.com/use-postgresql-airflow-dag/materials/bigdata_2.jpg)

 __Step : 3__   

 Connection id : postgres_localhost  -----> this should match with [postgres_db.py](/DAGS/Postgres_Connnection/postgres_db.py) line 23  

 connection type : Postgres  

 Host : postgres   -----> this should match with [docker compose.yml](/Airflow_Installation/docker%20compose.yml) line 62  

Login and password : same as [docker compose.yml](/Airflow_Installation/docker%20compose.yml)  line 65,66

Port : 5432  

![](https://chrischow.github.io/dataandstuff/graphics/2022-01-26-open-options-chains-part-iii/postgres_connection.jpg)  

__step : 4__ Save the Connection