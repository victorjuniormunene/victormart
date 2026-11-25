# VictorMart

## Overview
VictorMart is an online marketplace that connects customers with suppliers of retail products across Kenya.

## Features
- **User Roles**: The application supports three user roles: Admin, Customers, and Suppliers.
- **Supplier Functionality**: Suppliers can list and manage retail products, including prices and locations.
- **Customer Functionality**: Customers can browse products, place orders, track purchases, and manage their dashboards.

## Project Setup

### Prerequisites
- Python 3.x
- Django
- PostgreSQL (or any other database of your choice)

### Installation
1. Clone the repository:
   ```
   git clone <repository-url>
   cd victormart
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Set up your environment variables:
   - Copy `.env.example` to `.env` and fill in the required values.

5. Run migrations:
   ```
   python manage.py migrate
   ```

6. Create a superuser:
   ```
   python manage.py createsuperuser
   ```

7. Start the development server:
   ```
   python manage.py runserver
   ```

## Directory Structure
```
victormart/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── Dockerfile
├── construction_hub/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/
│   ├── suppliers/
│   ├── products/
│   ├── orders/
│   └── dashboard/
├── templates/
├── static/
├── docs/
└── tests/
```

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.