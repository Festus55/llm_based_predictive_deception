To convert from json to jsonl type use the command
```
jq -c '.[]' input.json > output.jsonl
```

To convert from jsonl to json type use the command
```
jq -s '.' input.jsonl > output.json
```