from datetime import datetime
import os
import shutil
import traceback
import joblib
import pandas as pd
import psycopg2
from sklearn.metrics import mean_absolute_error
from sqlalchemy import desc

from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split

from app.database import SessionLocal
from app.models.voice import VoiceInfoCollect
from app.util import calculate_duration_units
from app.config import settings

class PredictVoiceDuration:

    @staticmethod
    def train_data():
        db = SessionLocal()
        try:
            results = db.query(VoiceInfoCollect.spk_id)\
                        .filter(VoiceInfoCollect.spk_id.isnot(None))\
                        .distinct()\
                        .all()
            all_speakers = [row[0] for row in results]
            print(f'数据库中已有音色列表：{all_speakers}')
            for speaker in all_speakers:
                stmt = (
                    db.query(
                        VoiceInfoCollect.char_count,
                        VoiceInfoCollect.punc_count,
                        VoiceInfoCollect.audio_duration
                    )
                    .filter(VoiceInfoCollect.spk_id == speaker)
                    .order_by(desc(VoiceInfoCollect.id))
                    .limit(10000)
                    .statement
                )
                raw_sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
                conn = psycopg2.connect(settings.DATABASE_URL)

                try:
                    # 3. 把原生连接传给 pandas
                    df = pd.read_sql_query(raw_sql, conn)
                finally:
                    # 4. 记得关闭连接
                    conn.close()
                    
                if len(df) < 5:
                    print(f"⚠️ 音色 {speaker} 数据量仅 {len(df)} 条，跳过训练。")
                    continue

                X = df[['char_count', 'punc_count']]
                y = df['audio_duration']

                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
                model = LinearRegression()
                model.fit(X_train, y_train)
                
                # 评估模型
                y_pred = model.predict(X_test)
                mae = mean_absolute_error(y_test, y_pred)
                print(f"音色 {speaker} 的平均预测误差 (MAE): {mae:.2f} 秒")
                
                model_filename = f"tts_model_{speaker}.pkl"
                joblib.dump(model, model_filename)
                print(f"✅ 音色 {speaker} 模型动态更新成功！(基于最新的 {len(df)} 条数据)")

                if os.path.exists(model_filename):
                    backup_path = f"{model_filename}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(model_filename, backup_path)
                    print(f"📦 原文件已备份到: {backup_path}")
        except Exception as e:
            traceback.print_exc()
            print(f'train task failed. {str(e)}')
            raise e
        finally:
            db.close()

    @staticmethod
    def predict_model(spk_id, next_text):
        """
        输入音色和下一句文本，预测音频时长
        """
        # 1. 提取新文本的特征
        calc_result = calculate_duration_units(next_text)

        char_count = calc_result['char_count']
        punc_count = calc_result['punc_count']
        # X_new = [[char_count, punc_count]]
        X_new = pd.DataFrame([{
            'char_count': char_count, 
            'punc_count': punc_count
        }])
        
        # 2. 加载对应音色的模型
        try:
            model = joblib.load(f"tts_model_{spk_id}.pkl")
        except FileNotFoundError:
            # 如果该音色没有模型，返回-1
            return -1
        
        # 3. 预测并返回
        predicted_time = model.predict(X_new)[0]
        
        # 4. 边界防御：时长不可能小于 0 秒
        return max(0.5, round(predicted_time, 2))
    

def train_tts_predict_model():
    # PredictVoiceDuration.train_data()
    predict_duration = PredictVoiceDuration.predict_model(spk_id='zh_male_guanggaojieshuo_uranus_bigtts', next_text='有一个壮族人去赶集，走到半路，看见一个汉族人在犁田，就问：“欸，欸，欸！要水牛来犁田呀？')
    print(f'预测时长：{predict_duration} 秒')