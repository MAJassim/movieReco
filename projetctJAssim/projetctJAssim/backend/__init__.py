import logging
import azure.functions as func
import json
from datetime import datetime
from openai import AzureOpenAI
import pyodbc
from azure.communication.email import EmailClient

# Azure OpenAI API settings
api_key = "21B2PiWivuBdf5slTWNhRw4TiX7RyLLKut8KH0GXGK4xRka2zm7pJQQJ99ALACHYHv6XJ3w3AAAAACOGuDKX"
azure_endpoint = "https://mouss-m4uh339n-eastus2.cognitiveservices.azure.com/openai/deployments/gpt-4/chat/completions?api-version=2024-08-01-preview"
api_version = "2024-02-15-preview"

# Initialize the Azure OpenAI client
client = AzureOpenAI(
    azure_endpoint=azure_endpoint,
    api_key=api_key,
    api_version=api_version,
)

# Azure SQL Database Connection String
SQL_CONNECTION_STRING = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=tcp:movie-rec-server.database.windows.net,1433;"
    "Database=movie-db;"
    "Uid=jassim;"
    "Pwd=OUjda2003_10;"
    "Encrypt=yes;"
    "TrustServerCertificate=no;"
    "Connection Timeout=30;"
)

# Azure Communication Service connection string
EMAIL_CONNECTION_STRING = "endpoint=https://movie-mail.europe.communication.azure.com/;accesskey=9XK0JJIgPrksLgNgDxjZcor1JyAvGsqdu5JxuBupKCQ36bNbGrITJQQJ99ALACULyCpD2vV4AAAAAZCS3yCg"

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # Get parameters from request body
        body = req.get_json()
        category = body.get('category')
        email = body.get('email')

        if not category:
            return func.HttpResponse(
                "Please provide a movie category",
                status_code=400
            )

        if email and not validate_email(email):
            return func.HttpResponse(
                "Invalid email address provided.",
                status_code=400
            )

        # Generate movie recommendations
        recommendations = generate_recommendations(category)

        # Prepare data for storage and response
        movie_data = {
            "category": category,
            "recommendations": recommendations,
            "time": datetime.now().strftime("%Y-%m-%d %I:%M %p")
        }

        try:
            save_to_sql(movie_data)
            logging.info("Movie recommendations saved to database successfully.")
        except Exception as e:
            logging.error(f"Error saving data to SQL: {e}")
            return func.HttpResponse(
                "Failed to save recommendations to the database.",
                status_code=500
            )

        # Send email if provided
        if email:
            logging.info(f"Attempting to send email to: {email}")
            try:
                send_email(movie_data, email)  # Dynamically pass user-provided email
                logging.info(f"Email sent successfully to {email}.")
            except Exception as e:
                logging.error(f"Error sending email to {email}: {e}")

        return func.HttpResponse(
            json.dumps(movie_data),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"Error: {e}")
        return func.HttpResponse(
            "An error occurred processing your request.",
            status_code=500
        )

def validate_email(email: str) -> bool:
    import re
    pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    return re.match(pattern, email) is not None

def generate_recommendations(category: str) -> str:
    prompt = f"Recommend 5 must-watch movies in the {category} genre. For each movie, include a brief description and why it's worth watching."
    
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a helpful movie recommendation assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response.choices[0].message.content

def save_to_sql(movie_data: dict):
    try:
        conn = pyodbc.connect(SQL_CONNECTION_STRING)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO MovieRecommendations (Category, Recommendations, RequestTime)
            VALUES (?, ?, ?)
        """, (
            movie_data['category'],
            movie_data['recommendations'],
            movie_data['time']
        ))

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logging.error(f"Database Error: {e}")
        raise


def send_email(movie_data: dict, recipient_email: str):
    try:
        client = EmailClient.from_connection_string(EMAIL_CONNECTION_STRING)

        html_content = """
        <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h1>Movie Recommendations</h1>
                <h2>Category: {category}</h2>
                <div style="line-height: 1.6;">
                    {recommendations}
                </div>
                <p style="color: #666; font-size: 0.8em;">Generated on: {time}</p>
            </body>
        </html>
        """

        formatted_html = html_content.format(
            category=movie_data['category'].title(),
            recommendations=movie_data['recommendations'].replace('\n', '<br>'),
            time=movie_data['time']
        )

        message = {
            "senderAddress": "DoNotReply@2ddbcd2b-1604-4c13-8081-a036fec4595c.azurecomm.net",
            "recipients": {
                "to": [{"address": recipient_email}]  # Dynamic email recipient
            },
            "content": {
                "subject": f"Movie Recommendations - {movie_data['category'].title()} Movies",
                "plainText": f"Movie Recommendations for {movie_data['category']}:\n\n{movie_data['recommendations']}",
                "html": formatted_html
            }
        }

        poller = client.begin_send(message)
        result = poller.result()  # Wait for the result of the email send operation
        
        logging.info(f"Email sent successfully to {recipient_email}.")
    except Exception as ex:
        logging.error(f"Error sending email to {recipient_email}: {ex}")

