from transformers import MT5ForConditionalGeneration, MT5Tokenizer

# Cargar modelo entrenado
model_path = "./pln_model"
model = MT5ForConditionalGeneration.from_pretrained(model_path)
tokenizer = MT5Tokenizer.from_pretrained(model_path)

def predict(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    outputs = model.generate(**inputs, max_length=208)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

# Ejemplo de prueba
print(predict("consultá existencias impresoras Epson"))
print(predict("ajustar stock mouse logitech a 70"))
