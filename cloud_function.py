#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SceneValidator Cloud Function - Entry point for Google Cloud Functions deployment

This module provides a Cloud Functions-compatible entry point for the SceneValidator tool,
allowing it to be deployed as a serverless function in Google Cloud.
"""

import json
import logging
import os
import sys
from typing import Dict, Any, Optional, Tuple

import functions_framework
import google.cloud.logging
from flask import Request, jsonify
from google.cloud.logging.handlers import CloudLoggingHandler

from scene_validator import SceneValidator

# Set up logging
client = google.cloud.logging.Client()
handler = CloudLoggingHandler(client)
google.cloud.logging.handlers.setup_logging(handler)
logger = logging.getLogger("SceneValidator-CloudFunction")

# Initialize validator
config_path = os.environ.get("CONFIG_PATH")
validator = SceneValidator(config_path)
logger.info("SceneValidator Cloud Function initialized with config: %s", config_path)

@functions_framework.http
def scene_validator(request: Request) -> Tuple[Dict[str, Any], int, Dict[str, str]]:
    """
    HTTP Cloud Function for SceneValidator.
    
    Args:
        request: The HTTP request object
        
    Returns:
        The response text, or any set of values that can be turned into a Response object
    """
    # Set CORS headers for all requests
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Content-Type': 'application/json'
    }
    
    # Handle CORS preflight requests
    if request.method == 'OPTIONS':
        return ({}, 204, headers)
    
    # Route the request
    try:
        path = request.path
        
        if request.method == 'GET' and path == '/health':
            # Health check endpoint
            return (handle_health_check(), 200, headers)
            
        elif request.method == 'GET' and path.startswith('/validation/'):
            # Get validation results
            validation_id = path.split('/')[-1]
            return (handle_get_validation(validation_id), 200, headers)
            
        elif request.method == 'GET' and path.startswith('/project/') and path.endswith('/validations'):
            # Get project validations
            parts = path.split('/')
            if len(parts) >= 3:
                project_id = parts[2]
                return (handle_get_project_validations(project_id), 200, headers)
            else:
                return ({"error": "Invalid project ID"}, 400, headers)
                
        elif request.method == 'POST' and path == '/validate':
            # Validate scenes
            return handle_validate(request, headers)
            
        else:
            # Unknown endpoint
            return ({"error": f"Unsupported route: {request.method} {path}"}, 404, headers)
            
    except Exception as e:
        logger.exception("Error processing request: %s", e)
        return ({"error": str(e)}, 500, headers)

def handle_health_check() -> Dict[str, Any]:
    """Handle health check request."""
    from datetime import datetime
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": validator.config["project"]["version"]
    }

def handle_get_validation(validation_id: str) -> Dict[str, Any]:
    """Handle get validation request."""
    results = validator.get_validation(validation_id)
    
    if not results:
        return {"error": f"Validation {validation_id} not found"}
        
    return results

def handle_get_project_validations(project_id: str) -> Dict[str, Any]:
    """Handle get project validations request."""
    validations = validator.get_project_validations(project_id)
    
    return {
        "project_id": project_id,
        "validations": validations
    }

def handle_validate(request: Request, headers: Dict[str, str]) -> Tuple[Dict[str, Any], int, Dict[str, str]]:
    """Handle validate scenes request."""
    try:
        data = request.get_json()
        
        if not data:
            return ({"error": "Missing request body"}, 400, headers)
            
        project_id = data.get("project_id")
        scenes = data.get("scenes", [])
        validation_level = data.get("validation_level")
        
        if not project_id:
            return ({"error": "Missing project_id"}, 400, headers)
            
        if not scenes:
            return ({"error": "No scenes provided"}, 400, headers)
            
        # Log request info
        logger.info("Validation request for project %s with %d scenes at level %s",
                  project_id, len(scenes), validation_level)
        
        # Perform validation
        results = validator.validate_scenes(project_id, scenes, validation_level)
        
        return (results, 200, headers)
        
    except Exception as e:
        logger.exception("Error processing validation request: %s", e)
        return ({"error": str(e)}, 500, headers)