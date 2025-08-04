# Mail Server Security Scanner

Scan a list of domains to check for DNSSEC, DANE, and MTA-STS support 


## Results

[See blog post](https://alexsci.com/blog/is-email-confidential-in-transit-yet/)


## Running

    python3 -m venv venv
    source venv/bin/activate
    python manage.py makemigrations db
    python manage.py migrate
    echo "robalexdev.com" > list
    python analyze.py list
    python analyze.py

