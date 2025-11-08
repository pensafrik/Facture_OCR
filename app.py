from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from weasyprint import HTML
import base64
from datetime import datetime
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import io, re

# -----------------------
# App & Database Setup
# -----------------------
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:arouf1234@localhost/km_invoice'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# -----------------------
# Models
# -----------------------
class EtatTier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raison_sociale = db.Column(db.String(150), nullable=False)
    nature_tier = db.Column(db.String(100), nullable=False)
    ice = db.Column(db.String(50), nullable=False)
    if_field = db.Column(db.String(50), nullable=False)
    delai_paiement = db.Column(db.Integer)

class Achat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    client = db.Column(db.String(100), nullable=False)
    compteProduit = db.Column(db.String(100), nullable=False)
    devise = db.Column(db.String(60), nullable=False)
    dateFacturation = db.Column(db.String(20), nullable=False)
    montantHT = db.Column(db.Float, nullable=False)
    montantTVA = db.Column(db.Float, nullable=False)
    droitsTimbre = db.Column(db.Float, nullable=False)
    montantTTC = db.Column(db.Float, nullable=False)
    exported = db.Column(db.Boolean, default=False)

class OCRInvoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50))
    client = db.Column(db.String(150))
    compteProduit = db.Column(db.String(150))
    devise = db.Column(db.String(50))
    dateFacturation = db.Column(db.String(50))
    montantHT = db.Column(db.Float)
    montantTVA = db.Column(db.Float)
    droitsTimbre = db.Column(db.Float)
    montantTTC = db.Column(db.Float)

class Vente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    client = db.Column(db.String(150), nullable=False)
    compteProduit = db.Column(db.String(150), nullable=False)
    devise = db.Column(db.String(50))
    dateFacturation = db.Column(db.String(50))
    montantHT = db.Column(db.Float, nullable=False)
    montantTVA = db.Column(db.Float, nullable=False)
    droitsTimbre = db.Column(db.Float)
    montantTTC = db.Column(db.Float, nullable=False)
    exported = db.Column(db.Boolean, default=False)

class VenteOCRInvoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50))
    client = db.Column(db.String(150))
    compteProduit = db.Column(db.String(150))
    devise = db.Column(db.String(50))
    dateFacturation = db.Column(db.String(50))
    montantHT = db.Column(db.Float)
    montantTVA = db.Column(db.Float)
    droitsTimbre = db.Column(db.Float)
    montantTTC = db.Column(db.Float)

# -----------------------
# Helper Functions
# -----------------------
def safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def parse_date(val):
    try:
        return datetime.strptime(val, '%Y-%m-%d').date()
    except:
        return None

def extract_invoice_data(text):
    data = {}
    patterns = {
        "total_ht": r"TOTAL\s+H\.?T\.?\s*:? ?([0-9.,]+)",
        "total_ttc": r"TOTAL\s+T\.?T\.?C\.?\s*:? ?([0-9.,]+)",
        "total_tva": r"TOTAL\s+T\.?V\.?A\.?\s*:? ?([0-9.,]+)",
        "ice": r"ICE\s*:? ?([A-Z0-9]+)",
        "rc": r"\bRC\s*:? ?([A-Z0-9]+)",
        "if": r"\bIF\s*:? ?([A-Z0-9]+)"
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[key] = match.group(1)
    return data

def get_invoice_model(nature, ocr=False):
    """Return the correct SQLAlchemy model based on invoice type."""
    mapping = {
        'achat': Achat,
        'vente': Vente,
        'achat-ocr': OCRInvoice,
        'vente-ocr': VenteOCRInvoice
    }
    key = f"{nature}-ocr" if ocr else nature
    return mapping.get(key)

# -----------------------
# Routes
# -----------------------
@app.route('/')
def index():
    return render_template('invoice_editor.html')

# PDF generation
@app.route('/generate_pdf', methods=['POST'])
def generate_pdf():
    try:
        data = request.json
        data['quantity'] = safe_float(data.get('quantity', 0))
        data['unitPrice'] = safe_float(data.get('unitPrice', 0))
        html_content = render_template('invoice_pdf.html', data=data)
        pdf_bytes = HTML(string=html_content).write_pdf()
        encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        return jsonify({'pdf': encoded_pdf})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# -----------------------
# EtatTier routes
# -----------------------
@app.route('/etat-tier')
def etat_tier():
    tiers = EtatTier.query.all()
    return render_template('etat_tier.html', tiers=tiers)

@app.route('/etat-tier/add', methods=['POST'])
def add_tier():
    try:
        data = request.get_json()
        delai = data.get('delai_paiement')
        new_tier = EtatTier(
            raison_sociale=data['raison_sociale'],
            nature_tier=data['nature_tier'],
            ice=data['ice'],
            if_field=data['if_field'],
            delai_paiement=int(delai) if delai else None
        )
        db.session.add(new_tier)
        db.session.commit()
        return jsonify({'success': True, 'tier_id': new_tier.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/etat-tier/edit/<int:tier_id>', methods=['POST'])
def edit_tier(tier_id):
    try:
        tier = EtatTier.query.get_or_404(tier_id)
        data = request.get_json()
        tier.raison_sociale = data['raison_sociale']
        tier.nature_tier = data['nature_tier']
        tier.ice = data['ice']
        tier.if_field = data['if_field']
        tier.delai_paiement = parse_date(data.get('delai_paiement'))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/etat-tier/delete/<int:tier_id>', methods=['POST'])
def delete_tier(tier_id):
    try:
        tier = EtatTier.query.get_or_404(tier_id)
        db.session.delete(tier)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Achat OCR editor page
@app.route('/achat-invoice')
def achat_invoice_page():
    return render_template('achat_editor.html')

# Vente OCR editor page
@app.route('/vente-invoice')
def vente_invoice_page():
    return render_template('vente_editor.html')




# -----------------------
# Universal Invoice Save/Delete
# -----------------------
@app.route('/invoice/save', methods=['POST'])
def invoice_save():
    try:
        data = request.get_json()
        nature = data.get('natureFacture')  # 'achat', 'vente', 'achat-ocr', 'vente-ocr'
        model = get_invoice_model(nature, ocr='ocr' in nature)

        if not model:
            return jsonify({'success': False, 'error': 'Invalid natureFacture'}), 400

        invoice = model(
            numero=data.get('numero'),
            client=data.get('client'),
            compteProduit=data.get('compteProduit'),
            devise=data.get('devise'),
            dateFacturation=data.get('dateFacturation'),
            montantHT=safe_float(data.get('montantHT')),
            montantTVA=safe_float(data.get('montantTVA')),
            droitsTimbre=safe_float(data.get('droitsTimbre')),
            montantTTC=safe_float(data.get('montantTTC'))
        )
        db.session.add(invoice)
        db.session.commit()
        return jsonify({'success': True, 'invoice_id': invoice.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/invoice/delete', methods=['POST'])
def invoice_delete():
    try:
        data = request.get_json()
        nature = data.get('natureFacture')
        invoice_id = data.get('invoice_id')
        model = get_invoice_model(nature, ocr='ocr' in nature)
        if not model:
            return jsonify({'success': False, 'error': 'Invalid natureFacture'}), 400

        invoice = model.query.get_or_404(invoice_id)
        db.session.delete(invoice)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# -----------------------
# OCR File Parsing
# -----------------------
@app.route('/api/parse-invoice', methods=['POST'])
def parse_invoice():
    try:
        file = request.files['file']
        text = ""
        if file.filename.lower().endswith(".pdf"):
            pages = convert_from_bytes(file.read())
            for page in pages:
                text += pytesseract.image_to_string(page, lang="fra") + "\n"
        else:
            image = Image.open(io.BytesIO(file.read()))
            text = pytesseract.image_to_string(image, lang="fra")

        invoice_data = extract_invoice_data(text)
        return jsonify({"raw_text": text, "structured": invoice_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# --- Routes ---
@app.route('/achat', methods=['GET'])
def achats():
    invoices = Achat.query.filter_by(exported=False).all()
    return render_template('achat.html', invoices=invoices)
@app.route('/achat-exported')
def achat_exported():
    invoices = Achat.query.filter_by(exported=True).all()
    return render_template('achat_exported.html', invoices=invoices)

@app.route('/achat/add', methods=['POST'])
def add_achat():
    data = request.get_json()
    new_invoice = Achat(
        numero=data['numero'],
        client=data['client'],
        compteProduit=data['compteProduit'],
        devise=data['devise'],
        dateFacturation=data['dateFacturation'],
        montantHT=float(data['montantHT']),
        montantTVA=float(data['montantTVA']),
        droitsTimbre=float(data['droitsTimbre']),
        montantTTC=float(data['montantTTC'])
    )
    db.session.add(new_invoice)
    db.session.commit()
    return jsonify({'message': 'Invoice added successfully'})

@app.route('/achat/edit/<int:id>', methods=['PUT'])
def edit_achat(id):
    data = request.get_json()
    invoice = Achat.query.get_or_404(id)
    invoice.numero = data['numero']
    invoice.client = data['client']
    invoice.compteProduit = data['compteProduit']
    invoice.devise = data['devise']
    invoice.dateFacturation = data['dateFacturation']
    invoice.montantHT = float(data['montantHT'])
    invoice.montantTVA = float(data['montantTVA'])
    invoice.droitsTimbre = float(data['droitsTimbre'])
    invoice.montantTTC = float(data['montantTTC'])
    db.session.commit()
    return jsonify({'message': 'Invoice updated successfully'})
@app.route('/achat/export/<int:id>', methods=['POST'])
def export_achat(id):
    invoice = Achat.query.get_or_404(id)
    invoice.exported = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/achat/delete/<int:id>', methods=['DELETE'])
def delete_achat(id):
    invoice = Achat.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    return jsonify({'message': 'Invoice deleted successfully'})

# Vente CRUD
@app.route('/vente', methods=['GET'])
def vente_list():
    invoices = Achat.query.filter_by(exported=False).all()
    return render_template('vente.html', invoices=invoices)
@app.route('/vente/export/<int:id>', methods=['POST'])
def export_vente(id):
    invoice = Vente.query.get_or_404(id)
    invoice.exported = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/vente-exported', methods=['GET'])
def vente_exported():
    invoices = Vente.query.filter_by(exported=True).all()
    return render_template('vente_exported.html', invoices=invoices)


@app.route('/vente/add', methods=['POST'])
def add_vente():
    data = request.get_json()
    new_invoice = Vente(
        numero=data['numero'],
        client=data['client'],
        compteProduit=data['compteProduit'],
        devise=data['devise'],
        dateFacturation=data['dateFacturation'],
        montantHT=float(data['montantHT']),
        montantTVA=float(data['montantTVA']),
        droitsTimbre=float(data['droitsTimbre']),
        montantTTC=float(data['montantTTC'])
    )
    db.session.add(new_invoice)
    db.session.commit()
    return jsonify({'message': 'Invoice added successfully'})

@app.route('/vente/edit/<int:id>', methods=['PUT'])
def edit_vente(id):
    data = request.get_json()
    invoice = Vente.query.get_or_404(id)
    invoice.numero = data['numero']
    invoice.client = data['client']
    invoice.compteProduit = data['compteProduit']
    invoice.devise = data['devise']
    invoice.dateFacturation = data['dateFacturation']
    invoice.montantHT = float(data['montantHT'])
    invoice.montantTVA = float(data['montantTVA'])
    invoice.droitsTimbre = float(data['droitsTimbre'])
    invoice.montantTTC = float(data['montantTTC'])
    db.session.commit()
    return jsonify({'message': 'Invoice updated successfully'})

@app.route('/vente/delete/<int:id>', methods=['DELETE'])
def delete_vente(id):
    invoice = Vente.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    return jsonify({'message': 'Invoice deleted successfully'})


# -----------------------
# Run App
# -----------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
