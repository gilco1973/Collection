# Walkthrough: comm-templates

## 1. Run the live example

```
cd components/python/comm-templates && python3 example.py
```

An internal status update and a customer notice rendered from templates with a registry hash; a free-text field refused.

## 2. Copy and replace the texts

```
cp templates.py /path/to/your-service/
```

Replace the four templates with your process's and Compliance's wording. Keep `owner`, `audience`, `required` and `optional` on each; the customer template keeps its `disclosure`.

## 3. Let the model fill fields only

The model produces a dict of named fields; `render(ref, fields)` refuses unknown or missing ones. Free text never reaches a customer.

## 4. Post under the right role and tier

Posting a rendered update is a W1 tool under confirmation; the customer template is posted only by a principal with the communications role (a bundle rule). Record `registry_hash` with the action so a reviewer knows which text ran.

## 5. Prove it

```
python3 -m unittest discover -s tests -t . -v
```
