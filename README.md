# SceneValidator

Media automation tool for validating scene transitions and ensuring continuity across video and film projects.

## Overview

SceneValidator is a specialized media automation tool designed to validate scene transitions and ensure continuity across video and film projects. It analyzes scene metadata, transitions, and visual elements to identify inconsistencies or continuity errors.

## Features

- Validate scene transitions for timing and logical flow
- Check continuity of props, characters, and settings between scenes
- Identify potential continuity errors with varying severity levels
- Advanced continuity checking using Google Gemini API
- Multiple validation levels (basic, standard, thorough)
- RESTful API for integration with other systems
- Store validation history for projects

## Quick Start

### Prerequisites

1. Google Cloud Platform account
2. Python 3.9 or higher
3. Gemini API access
4. Google Cloud Storage bucket
5. Firestore database

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/dxaginfo/SceneValidator.git
   cd SceneValidator
   ```

2. Install required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Configure Google Cloud credentials:
   ```
   export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
   ```

4. Set up Gemini API key:
   ```
   export GEMINI_API_KEY=your_gemini_api_key
   ```

5. Copy and edit the configuration file:
   ```
   cp config.yaml config.local.yaml
   # Edit config.local.yaml with your project-specific settings
   ```

### Running the CLI Tool

```
python scene_validator.py --config config.local.yaml --input samples/scene_data.json --level standard
```

### Running the API Server

```
export CONFIG_PATH=config.local.yaml
python api.py
```

The API will be available at http://localhost:8080

## API Endpoints

### Validate Scenes
- **URL**: `/validate`
- **Method**: `POST`
- **Request Body**: JSON object matching the Input Schema
- **Response**: JSON object matching the Output Schema

### Get Validation Results
- **URL**: `/validation/{validation_id}`
- **Method**: `GET`
- **Response**: Validation results as JSON

### Get Project Validations
- **URL**: `/project/{project_id}/validations`
- **Method**: `GET`
- **Response**: List of validations for the project

## Input Schema

```json
{
  "project_id": "string",
  "scenes": [
    {
      "scene_id": "string",
      "timestamp": "number",
      "duration": "number",
      "location": "string",
      "time_of_day": "string",
      "characters": ["string"],
      "props": ["string"],
      "camera_angles": ["string"],
      "preceding_scene_id": "string",
      "following_scene_id": "string",
      "notes": "string"
    }
  ],
  "validation_level": "basic|standard|thorough"
}
```

## Output Schema

```json
{
  "project_id": "string",
  "validation_id": "string",
  "timestamp": "string",
  "validation_status": "pass|warning|fail",
  "issues": [
    {
      "issue_id": "string",
      "scene_id": "string",
      "issue_type": "continuity|transition|timing|metadata",
      "severity": "low|medium|high",
      "description": "string",
      "suggested_fix": "string"
    }
  ],
  "summary": {
    "total_scenes": "number",
    "scenes_validated": "number",
    "total_issues": "number",
    "critical_issues": "number"
  }
}
```

## Configuration

Configuration is done through a YAML file. See `config.yaml` for example settings.

## Integration with Other Tools

SceneValidator can be integrated with:

- **TimelineAssembler**: Use validation results to inform timeline assembly
- **ContinuityTracker**: Share continuity data between tools
- **StoryboardGen**: Validate storyboards against scene specifications
- **PostRenderCleaner**: Include validation steps in post-render workflow

## License

[MIT](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.