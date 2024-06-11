# postgres connection with webserver  
 __Step : 1__ Go to webserver page > admin > connections  

![](https://lh5.googleusercontent.com/H5RVZ2yZnxvK8j_3RYHOydb04ICXulQy2zYT9NFM7qSFJFoYZ5sa8d3lOR9v5A0AIp9rxKGVES_KL16LcgN-b2_tgOD1ULl3h3QcHVVospJH9fGI4V6ymNxoEceYH9dMqlrs-Xfs)  

 __Step : 2__ Tap on " + " to add new connection  

 ![](https://s3.amazonaws.com/recipes.dezyre.com/use-postgresql-airflow-dag/materials/bigdata_2.jpg)  


 __Step : 3__ 
   

 Connection Id : aws_s3_default   ----> this name should match with the [S3_Sensors.py](/DAGS/S3_Operator/S3_Sensors.py) line 23.

 Connection Type : AWS  

 Description : your choice  

 AWS Access Key ID :  Access key from AWS  
 
  [Click here to know how to create a new key](/DAGS/S3_Operator/AWS%20_Access%20&%20Secret_key_creation.md)

 AWS Secret Access Key : secret key from AWS

 ![](https://miro.medium.com/v2/resize:fit:1400/1*wu7glD1C5cU64NMA1Q2OnQ.png)  

 __Step : 4__ Save the connection 
