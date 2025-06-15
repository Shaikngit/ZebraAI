from flask import Flask, render_template, request, redirect, url_for, session
import requests
import json
from msal import PublicClientApplication
import re
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env if present

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_secret_key')  # Fallback for dev only

# --- Existing API sample logic (adapted) ---
experimentId = os.getenv('ZEBRA_EXPERIMENT_ID')
apiUrl = os.getenv('ZEBRA_API_URL')

# Get access token (interactive, for demo only)
def get_access_token():
    client_id = os.getenv('AZURE_CLIENT_ID')
    tenant_id = os.getenv('AZURE_TENANT_ID')
    if not client_id or not tenant_id:
        raise Exception('AZURE_CLIENT_ID and AZURE_TENANT_ID must be set in environment variables')
    app_msal = PublicClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        enable_broker_on_windows=True
    )
    result = app_msal.acquire_token_interactive(
        scopes=[os.getenv('AZURE_API_SCOPE', 'api://9021b3a5-1f0d-4fb7-ad3f-d6989f0432d8/.default')],
        parent_window_handle=app_msal.CONSOLE_WINDOW_HANDLE
    )
    if 'access_token' in result:
        return result['access_token']
    else:
        raise Exception('Failed to get access token')

def call_experiment_api(access_token, search_term):
    headers = {'Authorization': f'Bearer {access_token}','Content-Type':'application/json','Accept':'application/json'}
    run_model = {
        "DataSearchOptions": {"Search": search_term},
        "MaxNumberOfRows": 5
    }
    response = requests.post(f'{apiUrl}experiment/{experimentId}', headers=headers, data=json.dumps(run_model))
    if response.status_code == 200:
        data = response.json()
        # Extract cases from chatHistory assistant messages
        cases = []
        seen = set()
        chat_history = data.get('chatHistory', {}).get('messages', [])
        for msg in chat_history:
            if msg.get('role') == 'assistant' and msg.get('content'):
                content = msg['content']
                # Look for markdown table
                lines = content.splitlines()
                table_lines = [l for l in lines if l.strip().startswith('|')]
                if table_lines:
                    # Remove header and separator
                    table_data = table_lines[2:] if len(table_lines) > 2 else []
                    for row in table_data:
                        cols = [c.strip() for c in row.strip('|').split('|')]
                        if len(cols) >= 2 and cols[0] not in seen:
                            cases.append({
                                'CaseNumber': cols[0],
                                'Description': cols[1]
                            })
                            seen.add(cols[0])
                # If no table, try to extract single case info
                elif 'Case Number:' in content:
                    case_number = None
                    description = None
                    for line in lines:
                        if line.startswith('Case Number:'):
                            case_number = line.split(':',1)[1].strip()
                        if line.startswith('Issue:'):
                            description = line.split(':',1)[1].strip()
                    if case_number and case_number not in seen:
                        cases.append({'CaseNumber': case_number, 'Description': description or ''})
                        seen.add(case_number)
        data['Data'] = cases
        return data
    else:
        return {"error": "API call failed", "details": response.text}

# Dummy function for AI experiment results (replace with real logic as needed)
def get_ai_results(access_token, selected_case):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    payload = {
        "dataSearchKey": "",
        "dataSearchOptions": {
            "searchMode": "any",
            "search": selected_case,
            "filter": "",
            "orderBy": ""
        },
        "chatHistory": {
            "messages": []
        },
        "translatorLanguage": "",
        "translatorContent": "",
        "totalTokens": 0,
        "promptTokens": 0,
        "completionTokens": 0,
        "maxNumberOfRows": 1,
        "skipNumberOfRows": 0,
        "aiCallDuration": 0,
        "searchDuration": 0,
        "correlationId": None,  # Set to null
        "skipErrorRows": True,
        "sensitiveDoNotLog": True,
        "customFields": {},
        "chatFormatOptions": {},
        "functionDefinitions": "",
        "toolCalls": [],
        "answers": [],
        "experimentId": experimentId,
        "runInput": {}  # Add this field, adjust as needed per your API
    }
    # Use the v3 endpoint as shown in your ReDoc
    response = requests.post(f'{apiUrl}Experiment/v3', headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": "AI experiment API call failed", "details": response.text}

def parse_assistant_sections(ai_result):
    # Find the first assistant message with content
    assistant_msgs = ai_result.get('chatHistory', {}).get('messages', [])
    content = None
    for msg in assistant_msgs:
        if msg.get('role') == 'assistant' and msg.get('content'):
            content = msg['content']
            break
    if not content:
        return {}

    # Extract sections by label
    sections = {}
    current_label = None
    lines = content.splitlines()
    buffer = []
    for line in lines:
        match = re.match(r'^(Issue|Root Cause|Resolution|Summary|Reasons for Delay in Closure|Known Issue/Bug|References Used|Symptom\(s\)|Case Closure Status|Case Age and Delay Tag|Case Status|Known Issues or Bugs|References):', line)
        if match:
            if current_label and buffer:
                sections[current_label] = '\n'.join(buffer).strip()
            current_label = match.group(1)
            buffer = [line[len(current_label)+1:].strip()]
        else:
            if current_label:
                buffer.append(line)
    if current_label and buffer:
        sections[current_label] = '\n'.join(buffer).strip()

    # Extract Markdown table from any assistant message
    table = None
    for msg in assistant_msgs:
        if msg.get('role') == 'assistant' and msg.get('content'):
            lines = msg['content'].splitlines()
            table_lines = [l for l in lines if l.strip().startswith('|')]
            if table_lines:
                table = '\n'.join(table_lines)
                break
    sections['MarkdownTable'] = table
    return sections

# --- Flask routes ---
@app.route('/', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        case_number = request.form['case_number']
        access_token = get_access_token()
        results = call_experiment_api(access_token, case_number)
        print('DEBUG API RESPONSE:', results)  # Debug print
        return render_template('results.html', results=results, case_number=case_number, raw_response=json.dumps(results, indent=2))
    return render_template('search.html')

@app.route('/submit', methods=['POST'])
def submit():
    selected_case = request.form.get('selected_case')
    access_token = get_access_token()
    ai_result = get_ai_results(access_token, selected_case)
    sections = parse_assistant_sections(ai_result)
    return render_template('ai_results.html', ai_result=ai_result, sections=sections)

if __name__ == '__main__':
    app.run(debug=True)
