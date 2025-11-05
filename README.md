# Recognition Moments - Meeting Transcript Analysis

This project analyzes meeting transcripts using AWS Bedrock's Llama models to extract recognition-worthy contributions and insights from participants.

## 📋 Prerequisites

### 1. AWS Account Setup
- AWS account with access to Bedrock service
- AWS CLI configured or AWS credentials available
- Bedrock service enabled in `us-east-1` region
- Access to Llama model inference profiles

### 2. Python Environment
- Python 3.8+ installed
- pip package manager

## 🚀 Quick Start

### Step 1: Clone/Download the Repository
```bash
git clone https://github.com/deveshm13/Recognition-moments.git
cd transcript_GA
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure AWS Credentials

#### Environment Variables
```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="...."
export AWS_SESSION_TOKEN="..."
```

### Step 4: Run the Application
```bash
cd LLama-3
python app_llama3_3.py
```

## 📁 Project Structure

```
transcript_GA/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── .gitignore                        # Git ignore rules
├── app_llama.py                      # Main application script
├── Meeting_Transcripts/              # Meeting data
│   └── T_M_1.py                     # Sample meeting transcript
├── bedrock_model_results_Llama/      # Output directory (created automatically)
│   ├── Llama_4_Maverick_17B_Instruct_output.json
│   ├── Llama_4_Scout_17B_Instruct_output.json
│   ├── Llama_3_3_70B_Instruct_output.json
│   ├── Llama_3_2_90B_Vision_Instruct_output.json
│   └── summary_all_models.json
└── pretrained_model/                 # ML model files (ignored by git)
    └── lid.176.bin
```

## 🔧 Configuration

### Meeting Data
The application uses meeting transcript data from `Meeting_Transcripts/T_M_1.py`. To analyze different meetings:

1. Create a new transcript file in the `Meeting_Transcripts/` directory
2. Update the import statement in `app_llama.py`:
   ```python
   from Meeting_Transcripts.YOUR_FILE import meeting_transcript_1
   from Meeting_Transcripts.YOUR_FILE import meeting_attendance_report1
   ```

### Model Configuration
The application runs analysis on multiple Llama models. You can modify the `MODEL_LIST` in `app_llama.py` to include or exclude specific models.

## 📊 Output

The application generates:

1. **Individual Model Results**: Separate JSON files for each model in `bedrock_model_results_Llama/`
2. **Summary Report**: `summary_all_models.json` containing aggregated results from all models

### Output Structure
Each result includes:
- Model performance metrics (latency, token counts)
- Meeting context analysis
- Participant recognition scores and reasons
- Detailed contribution summaries

## 🛠️ Troubleshooting

### Common Issues

#### 1. AWS Authentication Error
```
Error: Unable to locate credentials
```
**Solution**: Verify AWS credentials are properly configured (see Step 4)

#### 2. Bedrock Access Denied
```
Error: User is not authorized to perform: bedrock:InvokeModel
```
**Solution**: Ensure your AWS account has Bedrock permissions and model access

#### 3. Module Import Error
```
ModuleNotFoundError: No module named 'boto3'
```
**Solution**: Ensure virtual environment is activated and dependencies are installed:
```bash
source .venv/bin/activate  # Activate venv
pip install -r requirements.txt
```

#### 4. Region Configuration Error
```
Error: Could not connect to the endpoint URL
```
**Solution**: Ensure you're using the correct region (`us-east-1`) and have Bedrock enabled

### Debug Mode
For detailed logging, modify the script to include error details:
```python
except Exception as e:
    print(f"Detailed error for {model_name}: {str(e)}")
    import traceback
    traceback.print_exc()
```

## 📝 Customization

### Adding New Models
To add support for additional Bedrock models:

1. Add model information to `MODEL_LIST`:
```python
{
    "name": "Your Model Name",
    "id": "arn:aws:bedrock:us-east-1:account:inference-profile/model-id"
}
```

### Modifying Analysis Parameters
Adjust the analysis behavior by modifying the `payload` parameters:
```python
payload = {
    "prompt": combined_prompt,
    "max_gen_len": 8192,        # Maximum response length
    "temperature": 0.2,         # Creativity level (0.0-1.0)
    "top_p": 0.9               # Sampling parameter
}
```

## 🔒 Security Notes

- Never commit AWS credentials to version control
- Use IAM roles with minimal required permissions
- Consider using AWS Secrets Manager for production deployments
- The `.gitignore` file excludes sensitive files and model binaries

## 📄 License

[Add your license information here]

## 🤝 Contributing

[Add contribution guidelines here]

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review AWS Bedrock documentation
3. Verify model availability in your region
4. Contact your AWS administrator for permission issues