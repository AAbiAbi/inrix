from flask import Flask, jsonify, request  # Add request to the imports

import requests
import os
import logging
from functools import lru_cache
import http.client
from service.geocoding_model import geocode_address
import json
from urllib.parse import urlencode


from datetime import datetime, timedelta
from urllib.parse import quote

app = Flask(__name__)
# Set this in your environment or app configuration
app.config['GEOCODING_API_KEY'] = 'your_geocoding_api_key_here'

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Environment variables
TOKEN_API_URL = os.getenv("TOKEN_API_URL", "http://localhost:8000/gettoken")

@app.route('/1')
def hello_world():
    return 'Hello, World!'

@app.route('/get-inrix-token')
@lru_cache(maxsize=1)
def get_inrix_token():
    try:
        response = requests.get(TOKEN_API_URL)
        # print("response" + response)
        if response.status_code == 200:
            token = response.json().get('token')
            if token:
                print(f"Token: {token}")  # Print the token for debugging
                app.logger.debug(f"Received token: {token}")
                return jsonify({"token": token})
            else:
                logging.error("Token not found in response")
                return jsonify({"error": "Token not found"}), 500
        else:
            logging.error(f"Error fetching token: {response.status_code}")
            return jsonify({"error": "Failed to fetch token"}), response.status_code
    except requests.RequestException as e:
        logging.error(f"Request exception: {e}")
        return jsonify({"error": "Request failed"}), 500



def get_valid_inrix_token():
    token_result = get_inrix_token()
    
    # If the result is a tuple, it indicates an error response was returned
    if isinstance(token_result, tuple):
        token_response, error_code = token_result
        return None, token_response, error_code
    
    # If the result is not a tuple, then a normal response object is assumed
    if token_result.status_code != 200:
        return None, jsonify({"error": "Failed to get INRIX token"}), token_result.status_code
    
    # Extract the token value from the token response
    token_data = token_result.get_json()
    token = token_data.get("token")
    
    if not token:
        return None, jsonify({"error": "Token is missing from the token response"}), 500
    
    return token, None, 200


@app.route('/route', methods=['GET'])
def route():
    # Obtain a fresh token
    # Get the token from the get_inrix_token function
    token, error_response, status_code = get_valid_inrix_token()
    if error_response:
        return error_response, status_code
    
    # Headers with the obtained token
    headers = {
        'Authorization': f'Bearer {token}'
    }

    # Use the token in the headers for the request
    conn = http.client.HTTPSConnection("api.iq.inrix.com")
    payload = ''
    

    # Print headers for debugging
    print("Headers being sent:", headers)

    conn.request("GET", "/findRoute?wp_1=37.770581%2C-122.442550&wp_2=37.765297%2C-122.442527&format=json", payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))
    if res.status == 200:
        return jsonify(data.decode("utf-8"))
    else:
        return jsonify({"error": data.decode("utf-8")}), res.status



@app.route('/quickpath', methods=['GET'])
def quickpath():
    start_lat = request.args.get('start_lat')
    start_lng = request.args.get('start_lng')
    end_lat = request.args.get('end_lat')
    end_lng = request.args.get('end_lng')
    # app.logger.debug(f'Type of start_lat: {type(start_lat).__name__}')

    token, error_response, status_code = get_valid_inrix_token()
    if error_response:
        return error_response, status_code

    if not all([start_lat, start_lng, end_lat, end_lng]):
        return jsonify({'error': 'Missing latitude or longitude parameters'}), 400

    result, status_code = get_route_from_inrix(start_lat, start_lng, end_lat, end_lng, token)
    if 'error' in result:
        return jsonify(result), status_code
    return jsonify(result), status_code 


@app.route('/schedule', methods=['GET'])
def schedule():
    # Sample waypoints - replace these with actual user inputs
    waypoints = [
        {'lat': 37.7749, 'lng': -122.4194},
        {'lat': 37.3382, 'lng': -121.8863},
        {'lat': 37.8044, 'lng': -122.2711},
        # Add more waypoints as needed
    ]

    token, error_response, status_code = get_valid_inrix_token()
    if error_response:
        return error_response, status_code

    schedule_list = []
    total_time = 0
    current_time = datetime.utcnow()

    for i in range(len(waypoints)-1):
        start_wp = waypoints[i]
        end_wp = waypoints[i+1]
        # Instead of calling the quickpath endpoint, call a function that performs its logic
        result, status_code = get_route_from_inrix(start_wp['lat'], start_wp['lng'], end_wp['lat'], end_wp['lng'], token)
       
        
        if 'error' in result:
            app.logger.debug(f"Error from INRIX: {result}")
            return jsonify(result), status_code
        
        # Extract travel time from the response
        travel_time = result['result']['trip']['routes'][0]['travelTimeMinutes']
        total_time += travel_time
        arrival_time = current_time + datetime.timedelta(minutes=total_time)
        
        # Append the leg to the schedule
        schedule.append({
            'from': start_wp,
            'to': end_wp,
            'departure_time': current_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'arrival_time': arrival_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'travel_time_minutes': travel_time
        })
        
        # Assume a 1 hour stay at each waypoint
        total_time += 60
        current_time += datetime.timedelta(minutes=60)

    return jsonify(schedule)

if __name__ == '__main__':
    app.run(debug=True)





def get_route_from_inrix(start_lat, start_lng, end_lat, end_lng, token):
    INRIX_ROUTE_URL = 'https://api.iq.inrix.com/findRoute'
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'wp_1': f"{start_lat},{start_lng}",
        'wp_2': f"{end_lat},{end_lng}",
        'format': 'json'
    }



    # # Log headers and params
    app.logger.debug(f'Headers: {headers}')
    # app.logger.debug(f'Params: {params}')

    try:
        response = requests.get(INRIX_ROUTE_URL, headers=headers, params=params)
        response.raise_for_status()  # This will raise an HTTPError if the HTTP request returned an unsuccessful status code
        return response.json(), 200  # We assume here that Inrix always responds with JSON
    except requests.HTTPError as http_err:
        app.logger.error(f'HTTP error occurred: {http_err}')
        return {"error": "HTTP error occurred while requesting INRIX route"}, response.status_code
    except Exception as err:
        app.logger.error(f'An error occurred: {err}')
        return {"error": "An error occurred while requesting INRIX route"}, 500


@app.route('/quickpath1', methods=['GET'])
def quickpath1():
    
    

    # request_url = f"/findRoute?wp_1={wp1['lat']}%2C{wp1['lng']}&wp_2={wp2['lat']}%2C{wp2['lng']}&format=json"
   
    token1, error_response, status_code = get_valid_inrix_token()
    if error_response:
        return error_response, status_code
    
    waypoints = [
        {'lat': 37.7749, 'lng': -122.4194},
        {'lat': 37.3382, 'lng': -121.8863},
        {'lat': 37.8044, 'lng': -122.2711},
        # Add more waypoints as needed
    ]

    wp11 = "37.7749"
    wp12 = "-122.4194"
    wp21 = "37.3382"
    wp22 = "-121.8863"
    # Format the request URL with the waypoint
        # Log the types of parameters
    
    result, status_code = get_route_from_inrix(wp11, wp12, wp21, wp22, token1)
    if 'error' in result:
        return jsonify(result), status_code
    return jsonify(result), status_code 

def format_request_url(lat1, lng1, lat2, lng2):
    # wp1 = f"{quote(str(lat1))},{quote(str(lng1))}"
    # wp2 = f"{quote(str(lat2))},{quote(str(lng2))}"

    params = {
        'wp_1': f"{lat1},{lng1}",
        'wp_2': f"{lat2},{lng2}",
        'format': 'json'
    }
    encoded_params = urlencode(params)
    return f"/findRoute?{encoded_params}"
    # return f"/findRoute?wp_1={wp1}&wp_2={wp2}&format=json"