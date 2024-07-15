# Initial Set-up of database

Start up `manage.py`.  
Assuming `$cerfServer` is the root directory of the project
```
$ source $cerfServer/.venv/bin/activate
$ $cerfServer/manage.py
```
Run `migrate` to create all the tables
```
manage.py@cerfServer> migrate
```

Create a superuser called `admin` that is used for initializing 
the static tables. 

```
manage.py@cerfServer> createsuperuser
```
Run `init_sql` and `init_gages` to initialize the static tables
```
manage.py@cerfServer> init_sql
manage.py@cerfServer> init_gages
```

# Updating
After pulling the latest updates from the repo, you should run `migrate` 
in case there have been any database changes
```
manage.py@cerfServer> migrate
```

# Running the server
To run the server outside of Pycharm, use `runCerf.sh`