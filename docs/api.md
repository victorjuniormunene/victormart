# API Documentation for VictorMart

## Overview
The VictorMart API allows customers to browse and order products from suppliers. The API supports admin, customer, and supplier accounts.

## Authentication
All API requests require authentication. Users must obtain a token by logging in with their credentials.

### Login
- **Endpoint:** `/api/login/`
- **Method:** POST
- **Request Body:**
  - `username`: string
  - `password`: string
- **Response:**
  - `token`: string

## User Roles
### Admin
- Can manage users, products, and orders.

### Customers
- Can view products and make orders.

### Suppliers
- Can post retail products with prices and locations.

## Endpoints

### Products
- **Get All Products**
  - **Endpoint:** `/api/products/`
  - **Method:** GET
  - **Response:** List of products with details (name, cost, location).

- **Create Product**
  - **Endpoint:** `/api/products/`
  - **Method:** POST
  - **Request Body:**
    - `name`: string
    - `cost`: decimal
    - `location`: string
  - **Response:** Created product details.

### Orders
- **Create Order**
  - **Endpoint:** `/api/orders/`
  - **Method:** POST
  - **Request Body:**
    - `product_id`: integer
    - `quantity`: integer
  - **Response:** Order confirmation details.

### User Dashboard
- **Get User Dashboard**
  - **Endpoint:** `/api/dashboard/`
  - **Method:** GET
  - **Response:** User-specific data including orders.

## Error Handling
The API returns standard HTTP status codes to indicate the success or failure of requests. Common error responses include:
- **400 Bad Request:** Invalid input data.
- **401 Unauthorized:** Authentication required.
- **404 Not Found:** Resource not found.
- **500 Internal Server Error:** Unexpected server error.

## Rate Limiting
To ensure fair usage, the API implements rate limiting. Users are limited to a certain number of requests per minute.

## Conclusion
This API documentation provides an overview of the VictorMart endpoints. For further details, please refer to the individual endpoint documentation or the source code.