# fotos
private photo album


# Apache mod_wsgi integration

## Create a dedicated user (optional)

```
useradd -m -s /bin/bash fotos
```

## Clone the repository

## Create a python venv

```
fotos@horus:~/fotos-app$ python3 -m venv .venv
fotos@horus:~/fotos-app$ source .venv/bin/activate
(.venv) fotos@horus:~/fotos-app$ pip install -r requirements.txt
```

## Apache config

https://modwsgi.readthedocs.io/en/develop/user-guides/virtual-environments.html#virtual-environment-and-python-version

Assuming app install path is /home/fotos/fotos the following VirtualHost config allows for daemon mode integration with apache

```
    WSGIDaemonProcess fotos user=fotos group=fotos threads=5 python-home=/home/fotos/fotos/.venv python-path=/home/fotos/fotos/fotos
    
    WSGIScriptAlias /photos /home/fotos/fotos/fotos/fotos.wsgi

    <Directory /home/fotos/fotos/fotos >
        WSGIProcessGroup fotos
        WSGIApplicationGroup %{GLOBAL}
        #Order deny,allow
        #Allow from all
        Require all granted
    </Directory>
```