import sqlite3
import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# 設定圖片上傳資料夾
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    return conn

# 初始化資料庫：確保 orders 資料表存在
def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            order_data TEXT NOT NULL,
            total_amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 確保 products 表有 variants 和 image_positions 欄位
    # 先檢查欄位是否存在，如果不存在就新增
    cursor = conn.execute("PRAGMA table_info(products)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'variants' not in columns:
        try:
            conn.execute("ALTER TABLE products ADD COLUMN variants TEXT DEFAULT '[]'")
            print("✅ 已新增 variants 欄位到 products 表")
        except:
            pass
    
    if 'image_positions' not in columns:
        try:
            conn.execute("ALTER TABLE products ADD COLUMN image_positions TEXT DEFAULT '[]'")
            print("✅ 已新增 image_positions 欄位到 products 表")
        except:
            pass

    if 'image_rotations' not in columns:
        try:
            conn.execute("ALTER TABLE products ADD COLUMN image_rotations TEXT DEFAULT '[]'")
            print("✅ 已新增 image_rotations 欄位到 products 表")
        except:
            pass
    
    conn.commit()
    conn.close()

# 啟動時初始化資料庫
init_db()

# --- 頁面路由 ---
@app.route('/')
def home():
    return send_from_directory('.', 'MOindex.html')

@app.route('/about')
def about():
    return send_from_directory('.', 'MOabout.html')

@app.route('/product')
def product(): # Note: Filename is MOproduct.html but route is /product usually
    return send_from_directory('.', 'MOproduct.html')

@app.route('/cart')
def cart():
    return send_from_directory('.', 'MOcart.html')

@app.route('/admin')
def admin_page():
    return send_from_directory('.', 'admin.html')


# --- 1. 取得所有商品 (API) ---
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()
    conn.close()
    
    products_list = []
    for p in products:
        p_dict = dict(p)
        # 把 JSON 字串轉回 Python 列表/物件
        try:
            p_dict['images'] = json.loads(p['images']) if p['images'] else []
            p_dict['variants'] = json.loads(p['variants']) if 'variants' in p_dict and p_dict['variants'] else []
            # 嘗試解析 category，如果是 JSON 陣列字串就轉成 list
            if p['category'] and isinstance(p['category'], str) and (p['category'].startswith('[') or '"' in p['category']):
                 try:
                     p_dict['category'] = json.loads(p['category'])
                 except:
                     pass
            
            p_dict['image_positions'] = json.loads(p['image_positions']) if 'image_positions' in p_dict and p_dict['image_positions'] else []
            p_dict['image_rotations'] = json.loads(p['image_rotations']) if 'image_rotations' in p_dict and p_dict['image_rotations'] else []
        except:
            pass # 如果解析失敗就維持原狀
        products_list.append(p_dict)
        
    return jsonify(products_list)

# --- 2. 取得單一商品詳情 (API) ---
@app.route('/api/products/<int:id>', methods=['GET'])
def get_product(id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (id,)).fetchone()
    conn.close()
    if product is None:
        return jsonify({'error': 'Product not found'}), 404
    
    p_dict = dict(product)
    try:
        p_dict['images'] = json.loads(p_dict['images']) if p_dict['images'] else []
        p_dict['variants'] = json.loads(p_dict['variants']) if 'variants' in p_dict and p_dict['variants'] else []
        # 嘗試解析 category
        if p_dict['category'] and isinstance(p_dict['category'], str) and (p_dict['category'].startswith('[') or '"' in p_dict['category']):
             try:
                 p_dict['category'] = json.loads(p_dict['category'])
             except:
                 pass
        
        p_dict['image_positions'] = json.loads(p_dict['image_positions']) if 'image_positions' in p_dict and p_dict['image_positions'] else []
        p_dict['image_rotations'] = json.loads(p_dict['image_rotations']) if 'image_rotations' in p_dict and p_dict['image_rotations'] else []
    except:
        pass
    return jsonify(p_dict)

# --- 3. 新增/修改商品 (Admin) ---
@app.route('/api/products', methods=['POST'])
@app.route('/api/products/<int:id>', methods=['PUT'])
def save_product(id=None):
    data = request.form
    name = data.get('name')
    price = data.get('price')
    description = data.get('description')
    
    # 處理分類
    categories = request.form.getlist('category')
    if len(categories) == 0 and data.get('category'):
        categories = [data.get('category')]
    category_str = json.dumps(categories, ensure_ascii=False)

    variants = data.get('variants', '[]')
    
    # 處理圖片位置
    positions = request.form.getlist('positions') # 這裡收到的是 list of strings, e.g. ["50% 50%", "20% 30%"]
    image_positions_json = json.dumps(positions)
    
    # 處理圖片旋轉
    rotations = request.form.getlist('rotations')
    image_rotations_json = json.dumps(rotations)
    
    # --- 圖片處理 ---
    # 1. 處理新上傳的檔案
    uploaded_files = request.files.getlist('photos')
    new_filenames = []
    
    for file in uploaded_files:
        if file and file.filename != '':
            filename = file.filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            # 改為相對路徑
            new_filenames.append(f"/uploads/{filename}")

    # 2. 處理「已存在的舊圖片」
    existing_images = request.form.getlist('existing_images')
    # 修正：如果舊圖片帶有 http 開頭（從舊數據來的），這裡最好也正規化，但暫時保留原樣或轉相對路徑比較安全
    # 為了簡單，假設前端傳來的就是它想要的字串
    
    final_images = existing_images + new_filenames
    
    main_image = final_images[0] if final_images else ''
    
    images_json = json.dumps(final_images)

    conn = get_db_connection()
    if id:
        conn.execute('''
            UPDATE products 
            SET name=?, price=?, category=?, description=?, image=?, images=?, variants=?, image_positions=?, image_rotations=?
            WHERE id=?
        ''', (name, price, category_str, description, main_image, images_json, variants, image_positions_json, image_rotations_json, id))
    else:
        conn.execute('''
            INSERT INTO products (name, price, category, description, image, images, variants, image_positions, image_rotations)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, price, category_str, description, main_image, images_json, variants, image_positions_json, image_rotations_json))
        
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

# --- 4. 刪除商品 ---
@app.route('/api/products/<int:id>', methods=['DELETE'])
def delete_product(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'deleted'})

# --- 5. 結帳 (Checkout) ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    customer_name = data.get('customerName', '未提供姓名')
    cart = data.get('cart', [])
    
    # 計算總金額
    total_amount = sum(item.get('price', 0) * item.get('quantity', 1) for item in cart)
    
    # 將購物車轉為 JSON 字串儲存
    order_data_json = json.dumps(cart, ensure_ascii=False)
    
    # 存入資料庫
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO orders (customer_name, order_data, total_amount)
        VALUES (?, ?, ?)
    ''', (customer_name, order_data_json, total_amount))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"✅ 新訂單 #{order_id}：{customer_name}，總金額 NT${total_amount}")
    return jsonify({'status': 'success', 'message': 'Order received', 'order_id': order_id})

# --- 6. 取得所有訂單 (Admin) ---
@app.route('/api/orders', methods=['GET'])
def get_orders():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders ORDER BY created_at DESC').fetchall()
    conn.close()
    
    orders_list = []
    for o in orders:
        o_dict = dict(o)
        # 把 JSON 字串轉回 Python 列表
        try:
            o_dict['order_data'] = json.loads(o['order_data']) if o['order_data'] else []
        except:
            o_dict['order_data'] = []
        orders_list.append(o_dict)
    
    return jsonify(orders_list)

# --- 7. 圖片庫 API ---
@app.route('/api/images', methods=['GET'])
def get_images():
    images = []
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                # 改為相對路徑
                images.append(f"/uploads/{filename}")
    return jsonify(images)

@app.route('/api/images', methods=['DELETE'])
def delete_image():
    filename = request.args.get('filename')
    if not filename:
        return jsonify({'error': 'Filename is required'}), 400
    
    # 安全性檢查：雖然 filename 應該只是檔名，但防範路徑遍歷
    filename = os.path.basename(filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return jsonify({'status': 'deleted'})
        except Exception as e:
            print(f"Error deleting file: {e}")
            return jsonify({'error': 'Failed to delete file'}), 500
    else:
        return jsonify({'error': 'File not found'}), 404

# --- 7. 顯示圖片 (Static Files) ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    # 使用環境變數的 PORT，預設 5001
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)