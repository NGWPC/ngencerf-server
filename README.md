# Initial Set-up of database

Run manage.py and create a superuser called `Admin` that is used for initializing 
the static tables. 
Assuming $certServer is the root directory of the project
```
$ source $cerfServer/.venv/bin/activate
$ $cerfServer/manage.py
manage.py@cerfServer> createsuperuser
```
Run `migrate` to create all the tables and then run `init_sql` and `init_gages`
```
manage.py@cerfServer> migrate
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