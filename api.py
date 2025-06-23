#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SceneValidator API - Flask web interface for SceneValidator

This module provides a RESTful API for the SceneValidator tool, allowing clients
to submit scene data for validation and retrieve validation results.
"""

import json
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler

from scene_validator import SceneValidator

# Load environment variables
load_dotenv()

# Set up logging
client = google.cloud.logging.Client()
handler = CloudLoggingHandler(client)
google.cloud.logging.handlers.setup_logging(handler)
logger = logging.getLogger("SceneValidator-API")

# Create Flask app
app = Flask(__name__)
CORS(app)

# Initialize validator
config_path = os.environ.get("CONFIG_PATH")
validator = SceneValidator(config_path)
logger.info("SceneValidator API initialized with config: %s", config_path)

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": validator.config["project"]["version"]
    })

@app.route("/validate", methods=["POST"])
def validate():
    """
    Validate scenes API endpoint.
    
    Expects a JSON request body with:
    - project_id: string
    - scenes: array of scene objects
    - validation_level: string (optional, default from config)
    
    Returns:
    - Validation results as JSON
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "error": "Missing request body"
            }), 400
            
        project_id = data.get("project_id")
        scenes = data.get("scenes", [])
        validation_level = data.get("validation_level")
        
        if not project_id:
            return jsonify({
                "error": "Missing project_id"
            }), 400
            
        if not scenes:
            return jsonify({
                "error": "No scenes provided"
            }), 400
            
        # Log request info
        logger.info("Validation request for project %s with %d scenes at level %s",
                  project_id, len(scenes), validation_level)
        
        # Perform validation
        results = validator.validate_scenes(project_id, scenes, validation_level)
        
        return jsonify(results)
        
    except Exception as e:
        logger.exception("Error processing validation request: %s", e)
        return jsonify({
            "error": str(e)
        }), 500

@app.route("/validation/<validation_id>", methods=["GET"])
def get_validation(validation_id):
    """
    Get a specific validation result.
    
    Args:
        validation_id: ID of the validation to retrieve
        
    Returns:
        Validation results as JSON
    """
    try:
        results = validator.get_validation(validation_id)
        
        if not results:
            return jsonify({
                "error": f"Validation {validation_id} not found"
            }), 404
            
        return jsonify(results)
        
    except Exception as e:
        logger.exception("Error retrieving validation %s: %s", validation_id, e)
        return jsonify({
            "error": str(e)
        }), 500

@app.route("/project/<project_id>/validations", methods=["GET"])
def get_project_validations(project_id):
    """
    Get all validations for a project.
    
    Args:
        project_id: ID of the project
        
    Returns:
        List of validation summaries as JSON
    """
    try:
        validations = validator.get_project_validations(project_id)
        
        return jsonify({
            "project_id": project_id,
            "validations": validations
        })
        
    except Exception as e:
        logger.exception("Error retrieving validations for project %s: %s", project_id, e)
        return jsonify({
            "error": str(e)
        }), 500

def main():
    """Run the Flask app for local development."""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    main()