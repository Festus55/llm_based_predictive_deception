import json
import ast

input_filename = '../../../dataset/enriched_data/previsions.jsonl'
output_filename = '../../../dataset/enriched_data/training_set.json'
output_error_filename = '../../../dataset/enriched_data/distilled_errors_bis.json'

valid_records = 0
errors = 0
first_item = True # comma handling flag

def robust_json_parse(json_str):
    """
    Cascade parsing methods
    """
    json_str = json_str.replace('```json', '').replace('```', '').strip()
    
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        pass

    try:
        fixed_str = json_str.replace('\\\\"', '\\"')
        return json.loads(fixed_str, strict=False)
    except json.JSONDecodeError:
        pass
        
    py_friendly_str = json_str.replace('true', 'True').replace('false', 'False').replace('null', 'None')
    try:
        return ast.literal_eval(py_friendly_str)
    except (ValueError, SyntaxError):
        pass

    raise ValueError("All parsing strategies failed.")

def extract_input_from_prompt(prompt_text):
    """
    Extract the input through its marker
    """
    marker = "Trap deployment should not degrade honeypot responsiveness"
    
    idx = prompt_text.rfind(marker)
    if idx == -1: 
        return None, "Marker 'Trap deployment...' not found"
    
    post_marker_text = prompt_text[idx + len(marker):]
    
    output_key_idx = post_marker_text.find('"output":')
    if output_key_idx == -1:
        output_key_idx = post_marker_text.find("'output':")
    
    if output_key_idx == -1:
        return None, "Key 'output': not found"
        
    raw_input_segment = post_marker_text[:output_key_idx].strip()
    
    if raw_input_segment.endswith(','):
        raw_input_segment = raw_input_segment[:-1].strip()
        
    if not raw_input_segment.endswith('}'):
        raw_input_segment += '}'
        
    start_brace = raw_input_segment.find('{')
    if start_brace != -1:
        raw_input_segment = raw_input_segment[start_brace:]
    else:
        return None, "Starting { symbol not found"

    try:
        # Parsa il segmento come JSON
        obj = json.loads(raw_input_segment)
        # Ritorna il valore della chiave "input"
        return obj.get('input'), None
    except Exception as e:
        return None, f"Error, input parsing failed: {e}"



with open(input_filename, 'r') as f, \
     open(output_filename, 'w') as out, \
     open(output_error_filename, 'w') as er_out:
    
    out.write('[\n')

    for i, line in enumerate(f):
        line = line.strip()
        if not line: continue 
        try:
            data = json.loads(line)
            
            inner_json_str = data['response']['candidates'][0]['content']['parts'][0]['text']

            inner_data = robust_json_parse(inner_json_str)
            
            if 'request' not in data:
                raise ValueError("Campo 'request' mancante")
                
            prompt_text = data['request']['contents'][0]['parts'][0]['text']
            original_input, err_msg = extract_input_from_prompt(prompt_text)
            
            if err_msg:
                raise ValueError(f"Input extraction error: {err_msg}")

            final_obj = {}

            if isinstance(inner_data, list):
                final_obj = {
                    "input": original_input,
                    "output": inner_data
                }
            elif isinstance(inner_data, dict):
                if "input" in inner_data and "output" in inner_data:
                    content = inner_data['output']
                    output = content if isinstance(content, list) else [content]
                    final_obj = {
                    "input": original_input,
                    "output": output
                }
            
            if not first_item:
                out.write(',\n')
            
            out.write(json.dumps(final_obj, indent=2, ensure_ascii=False))
            
            first_item = False
            valid_records += 1
                                
        except Exception as e:
            errors += 1
            er_out.write(line + "\n")
            print(f"Skipped line number {i+1} (error: {e})")

    out.write('\n]')

print(f"\nParsing completed, {valid_records} records in '{output_filename}'.")
print(f"Skipped lines: {errors}")