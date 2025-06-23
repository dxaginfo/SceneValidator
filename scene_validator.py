#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SceneValidator - Media automation tool for validating scene transitions and continuity

This module provides the core functionality for validating scenes in video/film projects,
ensuring proper continuity between scenes, detecting transition issues, and maintaining
consistent visual elements.
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

import google.cloud.storage
from google.cloud import firestore
import yaml
import requests

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SceneValidator")

class SceneValidator:
    """
    Main class for validating scene transitions and continuity in media projects.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the SceneValidator with configuration.
        
        Args:
            config_path: Path to the configuration YAML file
        """
        self.config = self._load_config(config_path)
        self.gemini_api_key = os.environ.get(
            self.config["gemini"]["api_key_env"],
            ""
        )
        self.db = firestore.Client(project=self.config["google_cloud"]["project_id"])
        self.storage_client = google.cloud.storage.Client(
            project=self.config["google_cloud"]["project_id"]
        )
        self.bucket = self.storage_client.bucket(self.config["google_cloud"]["bucket_name"])
        logger.info("SceneValidator initialized with config: %s", config_path)

    @staticmethod
    def _load_config(config_path: Optional[str]) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to the configuration file
            
        Returns:
            Dict containing configuration parameters
        """
        default_config = {
            "project": {
                "name": "SceneValidator",
                "version": "1.0.0",
            },
            "google_cloud": {
                "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
                "region": "us-central1",
                "bucket_name": "scene-validator-storage",
            },
            "gemini": {
                "api_key_env": "GEMINI_API_KEY",
                "model": "gemini-pro-vision",
            },
            "validation": {
                "default_level": "standard",
                "timeout_seconds": 120,
                "max_scenes_per_batch": 50,
            }
        }
        
        if not config_path:
            logger.warning("No config path provided, using default configuration")
            return default_config
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                logger.info("Loaded configuration from %s", config_path)
                return config
        except Exception as e:
            logger.error("Failed to load config from %s: %s", config_path, e)
            return default_config

    def validate_scenes(self, project_id: str, scenes: List[Dict[str, Any]], 
                        validation_level: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate scenes for continuity and transition issues.
        
        Args:
            project_id: Unique identifier for the project
            scenes: List of scene dictionaries containing metadata
            validation_level: Level of validation to perform (basic, standard, thorough)
            
        Returns:
            Dictionary containing validation results
        """
        validation_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        # Use default validation level if not specified
        if not validation_level:
            validation_level = self.config["validation"]["default_level"]
            
        logger.info("Starting validation %s for project %s with %d scenes at level %s", 
                   validation_id, project_id, len(scenes), validation_level)
        
        # Initialize validation results
        results = {
            "project_id": project_id,
            "validation_id": validation_id,
            "timestamp": timestamp,
            "validation_status": "pass",
            "issues": [],
            "summary": {
                "total_scenes": len(scenes),
                "scenes_validated": 0,
                "total_issues": 0,
                "critical_issues": 0
            }
        }
        
        # Check if number of scenes exceeds maximum batch size
        if len(scenes) > self.config["validation"]["max_scenes_per_batch"]:
            logger.warning("Number of scenes (%d) exceeds max batch size (%d)", 
                          len(scenes), self.config["validation"]["max_scenes_per_batch"])
            results["issues"].append({
                "issue_id": str(uuid.uuid4()),
                "scene_id": None,
                "issue_type": "metadata",
                "severity": "medium",
                "description": f"Number of scenes ({len(scenes)}) exceeds maximum batch size " +
                              f"({self.config['validation']['max_scenes_per_batch']})",
                "suggested_fix": "Split validation into multiple smaller batches"
            })
            results["validation_status"] = "warning"
            results["summary"]["total_issues"] += 1
            
        # Validate each scene
        scene_map = {scene["scene_id"]: scene for scene in scenes}
        
        for scene in scenes:
            scene_id = scene.get("scene_id")
            if not scene_id:
                continue
                
            # Validate individual scene
            scene_issues = self._validate_scene(scene, scene_map, validation_level)
            
            # Add issues to results
            results["issues"].extend(scene_issues)
            results["summary"]["scenes_validated"] += 1
            results["summary"]["total_issues"] += len(scene_issues)
            
            # Count critical issues
            critical_issues = sum(1 for issue in scene_issues if issue["severity"] == "high")
            results["summary"]["critical_issues"] += critical_issues
            
            # Update validation status if issues are found
            if critical_issues > 0:
                results["validation_status"] = "fail"
            elif len(scene_issues) > 0 and results["validation_status"] != "fail":
                results["validation_status"] = "warning"
        
        # Store validation results in Firestore
        self._store_validation_results(results)
        
        logger.info("Completed validation %s with status %s, found %d issues (%d critical)",
                   validation_id, results["validation_status"], 
                   results["summary"]["total_issues"],
                   results["summary"]["critical_issues"])
        
        return results

    def _validate_scene(self, scene: Dict[str, Any], scene_map: Dict[str, Dict[str, Any]],
                       validation_level: str) -> List[Dict[str, Any]]:
        """
        Validate a single scene for continuity and transition issues.
        
        Args:
            scene: Dictionary containing scene metadata
            scene_map: Dictionary mapping scene IDs to scene data
            validation_level: Level of validation to perform
            
        Returns:
            List of issues found in the scene
        """
        issues = []
        scene_id = scene.get("scene_id", "unknown")
        
        # Basic validation - check for required fields
        required_fields = ["scene_id", "timestamp", "duration", "location"]
        for field in required_fields:
            if field not in scene or scene[field] is None:
                issues.append({
                    "issue_id": str(uuid.uuid4()),
                    "scene_id": scene_id,
                    "issue_type": "metadata",
                    "severity": "high",
                    "description": f"Missing required field: {field}",
                    "suggested_fix": f"Add {field} to scene metadata"
                })
        
        # Check for timestamp and duration validity
        if "timestamp" in scene and "duration" in scene:
            if not isinstance(scene["timestamp"], (int, float)):
                issues.append({
                    "issue_id": str(uuid.uuid4()),
                    "scene_id": scene_id,
                    "issue_type": "metadata",
                    "severity": "medium",
                    "description": "Timestamp is not a number",
                    "suggested_fix": "Convert timestamp to a numeric value (seconds)"
                })
                
            if not isinstance(scene["duration"], (int, float)) or scene["duration"] <= 0:
                issues.append({
                    "issue_id": str(uuid.uuid4()),
                    "scene_id": scene_id,
                    "issue_type": "metadata",
                    "severity": "medium",
                    "description": "Duration is not a positive number",
                    "suggested_fix": "Set duration to a positive numeric value (seconds)"
                })
        
        # Check scene references
        preceding_id = scene.get("preceding_scene_id")
        following_id = scene.get("following_scene_id")
        
        if preceding_id and preceding_id not in scene_map:
            issues.append({
                "issue_id": str(uuid.uuid4()),
                "scene_id": scene_id,
                "issue_type": "continuity",
                "severity": "high",
                "description": f"Referenced preceding scene {preceding_id} not found",
                "suggested_fix": "Add the missing scene or correct the reference"
            })
        
        if following_id and following_id not in scene_map:
            issues.append({
                "issue_id": str(uuid.uuid4()),
                "scene_id": scene_id,
                "issue_type": "continuity",
                "severity": "high",
                "description": f"Referenced following scene {following_id} not found",
                "suggested_fix": "Add the missing scene or correct the reference"
            })
        
        # Check for timing continuity
        if preceding_id and preceding_id in scene_map:
            preceding_scene = scene_map[preceding_id]
            if "timestamp" in preceding_scene and "duration" in preceding_scene and "timestamp" in scene:
                expected_timestamp = preceding_scene["timestamp"] + preceding_scene["duration"]
                if abs(expected_timestamp - scene["timestamp"]) > 0.001:  # Allow for floating point imprecision
                    issues.append({
                        "issue_id": str(uuid.uuid4()),
                        "scene_id": scene_id,
                        "issue_type": "timing",
                        "severity": "medium",
                        "description": f"Timing gap between scenes: expected {expected_timestamp}, got {scene['timestamp']}",
                        "suggested_fix": f"Adjust timestamp to {expected_timestamp} or add a transition scene"
                    })
        
        # Standard validation level checks
        if validation_level in ["standard", "thorough"]:
            # Check for time-of-day consistency
            if preceding_id and preceding_id in scene_map:
                preceding_scene = scene_map[preceding_id]
                if "time_of_day" in preceding_scene and "time_of_day" in scene:
                    if preceding_scene["time_of_day"] != scene["time_of_day"]:
                        # This could be intentional, so mark as low severity
                        issues.append({
                            "issue_id": str(uuid.uuid4()),
                            "scene_id": scene_id,
                            "issue_type": "continuity",
                            "severity": "low",
                            "description": f"Time of day changed from {preceding_scene['time_of_day']} to {scene['time_of_day']}",
                            "suggested_fix": "Ensure the time change is intentional and logically explained"
                        })
            
            # Check for prop continuity
            if preceding_id and preceding_id in scene_map:
                preceding_scene = scene_map[preceding_id]
                if "props" in preceding_scene and "props" in scene:
                    # Look for props that might have disappeared illogically
                    for prop in preceding_scene["props"]:
                        if prop not in scene["props"] and scene.get("location") == preceding_scene.get("location"):
                            issues.append({
                                "issue_id": str(uuid.uuid4()),
                                "scene_id": scene_id,
                                "issue_type": "continuity",
                                "severity": "low",
                                "description": f"Prop '{prop}' present in previous scene but missing in current scene",
                                "suggested_fix": "Add the prop or justify its absence in the scene"
                            })
        
        # Thorough validation with Gemini API for advanced continuity checks
        if validation_level == "thorough" and self.gemini_api_key:
            gemini_issues = self._validate_with_gemini(scene, scene_map)
            issues.extend(gemini_issues)
        
        return issues

    def _validate_with_gemini(self, scene: Dict[str, Any], 
                            scene_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Use Gemini API to perform advanced continuity validation.
        
        Args:
            scene: Dictionary containing scene metadata
            scene_map: Dictionary mapping scene IDs to scene data
            
        Returns:
            List of issues found by Gemini AI
        """
        issues = []
        scene_id = scene.get("scene_id", "unknown")
        
        try:
            # Prepare context for Gemini API
            preceding_id = scene.get("preceding_scene_id")
            following_id = scene.get("following_scene_id")
            
            context = {
                "current_scene": scene,
                "preceding_scene": scene_map.get(preceding_id) if preceding_id else None,
                "following_scene": scene_map.get(following_id) if following_id else None
            }
            
            # Call Gemini API for advanced analysis
            gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config['gemini']['model']}:generateContent"
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.gemini_api_key
            }
            
            prompt = """
            Analyze the continuity and logical flow between these scenes in a film/video project.
            Identify any potential continuity issues, logical inconsistencies, or narrative problems.
            Format your response as a JSON array of issues, where each issue has:
            - issue_type: "continuity", "transition", "timing", or "metadata"
            - severity: "low", "medium", or "high"
            - description: A clear explanation of the issue
            - suggested_fix: A practical suggestion to address the issue
            
            Only identify actual issues, not hypothetical ones. If no issues are found, return an empty array.
            """
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"text": json.dumps(context, indent=2)}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "topP": 0.8,
                    "topK": 40,
                    "maxOutputTokens": 1024
                }
            }
            
            response = requests.post(
                gemini_url,
                headers=headers,
                json=payload,
                timeout=self.config["validation"]["timeout_seconds"]
            )
            
            if response.status_code == 200:
                result = response.json()
                if "candidates" in result and result["candidates"]:
                    text_content = result["candidates"][0]["content"]["parts"][0]["text"]
                    try:
                        gemini_issues = json.loads(text_content)
                        if isinstance(gemini_issues, list):
                            for issue in gemini_issues:
                                # Add scene ID and issue ID to each issue
                                issue["scene_id"] = scene_id
                                issue["issue_id"] = str(uuid.uuid4())
                                issues.append(issue)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse Gemini API response as JSON: %s", text_content)
            else:
                logger.error("Gemini API request failed: %s", response.text)
                issues.append({
                    "issue_id": str(uuid.uuid4()),
                    "scene_id": scene_id,
                    "issue_type": "metadata",
                    "severity": "low",
                    "description": "Advanced validation with Gemini API failed",
                    "suggested_fix": "Check Gemini API access and retry"
                })
                
        except Exception as e:
            logger.error("Error during Gemini validation: %s", e)
            issues.append({
                "issue_id": str(uuid.uuid4()),
                "scene_id": scene_id,
                "issue_type": "metadata",
                "severity": "low",
                "description": f"Advanced validation error: {str(e)}",
                "suggested_fix": "Check system logs and retry"
            })
            
        return issues

    def _store_validation_results(self, results: Dict[str, Any]) -> None:
        """
        Store validation results in Firestore and Cloud Storage.
        
        Args:
            results: Dictionary containing validation results
        """
        validation_id = results["validation_id"]
        project_id = results["project_id"]
        
        try:
            # Store in Firestore
            doc_ref = self.db.collection("validations").document(validation_id)
            doc_ref.set(results)
            
            # Store in project history
            project_ref = self.db.collection("projects").document(project_id)
            project_ref.collection("validations").document(validation_id).set(results)
            
            # Store full results in Cloud Storage
            blob = self.bucket.blob(f"validations/{project_id}/{validation_id}.json")
            blob.upload_from_string(
                json.dumps(results, indent=2),
                content_type="application/json"
            )
            
            logger.info("Stored validation results with ID %s for project %s", 
                       validation_id, project_id)
                       
        except Exception as e:
            logger.error("Failed to store validation results: %s", e)

    def get_validation(self, validation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a validation by ID.
        
        Args:
            validation_id: Unique identifier for the validation
            
        Returns:
            Dictionary containing validation results or None if not found
        """
        try:
            doc_ref = self.db.collection("validations").document(validation_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                logger.warning("Validation %s not found", validation_id)
                return None
                
        except Exception as e:
            logger.error("Error retrieving validation %s: %s", validation_id, e)
            return None

    def get_project_validations(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all validations for a project.
        
        Args:
            project_id: Unique identifier for the project
            
        Returns:
            List of validation summary dictionaries
        """
        try:
            project_ref = self.db.collection("projects").document(project_id)
            validations = project_ref.collection("validations").stream()
            
            return [doc.to_dict() for doc in validations]
            
        except Exception as e:
            logger.error("Error retrieving validations for project %s: %s", project_id, e)
            return []


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="SceneValidator")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--input", help="Path to input JSON file")
    parser.add_argument("--output", help="Path to output JSON file")
    parser.add_argument("--level", choices=["basic", "standard", "thorough"],
                      default="standard", help="Validation level")
    
    args = parser.parse_args()
    
    # Initialize validator
    validator = SceneValidator(args.config)
    
    if args.input:
        try:
            with open(args.input, 'r') as f:
                data = json.load(f)
                
            project_id = data.get("project_id", "unknown")
            scenes = data.get("scenes", [])
            
            results = validator.validate_scenes(project_id, scenes, args.level)
            
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(results, f, indent=2)
                print(f"Results written to {args.output}")
            else:
                print(json.dumps(results, indent=2))
                
        except Exception as e:
            logger.error("Error processing input file: %s", e)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()