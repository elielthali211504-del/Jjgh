from pyobigram.utils import sizeof_fmt, get_file_size, createID, nice_time
from pyobigram.client import ObigramClient, inlineQueryResultArticle
from MoodleClient import MoodleClient
from JDatabase import JsonDatabase
import zipfile
import os
import infos
import xdlink
import mediafire
import datetime
import time
import youtube
import NexCloudClient
from pydownloader.downloader import Downloader
from ProxyCloud import ProxyCloud
import ProxyCloud
import requests
import S5Crypto
import traceback
import random
import pytz
import threading

# CONFIGURACIÓN FIJA DEL BOT
BOT_TOKEN = "8410047906:AAGntGHmkIuIvovBMQfy-gko2JTw3TNJsak"

# ADMINISTRADOR
ADMIN_USERNAME = "Eliel_21"

# ZONA HORARIA DE CUBA
try:
    CUBA_TZ = pytz.timezone('America/Havana')
except:
    CUBA_TZ = None

# SEPARADOR PARA EVIDENCIAS DE USUARIO
USER_EVIDENCE_MARKER = " "

# PRE-CONFIGURACIÓN DE USUARIOS
PRE_CONFIGURATED_USERS = {
    "Thali355,Eliel_21,Kev_inn10": {
        "cloudtype": "moodle",
        "moodle_host": "https://moodle.instec.cu/",
        "moodle_repo_id": 3,
        "moodle_user": "eliel2222",
        "moodle_password": "ElielThali2115.",
        "zips": 1023,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    },
    "thu,Satoru_2115": {
        "cloudtype": "moodle",
        "moodle_host": "https://cursos.uo.edu.cu/",
        "moodle_repo_id": 4,
        "moodle_user": "desiderio.vazquez",
        "moodle_password": "ThaliEliel1521.",
        "zips": 99,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    },
    "gatitoo_miauu,RancesCuit,SchnauzerMinnie,DARKBRAI,yordante,THE4L3X_08": {
        "cloudtype": "moodle",
        "moodle_host": "https://caipd.ucf.edu.cu/",
        "moodle_repo_id": 5,
        "moodle_user": "eliel21",
        "moodle_password": "ElielThali2115.",
        "zips": 99,
        "uploadtype": "evidence",
        "proxy": "",
        "tokenize": 0
    }
}

# ==============================
# SISTEMA DE CACHÉ PARA OPTIMIZACIÓN
# ==============================

class CloudCache:
    """Sistema de caché para evitar refrescos innecesarios"""
    def __init__(self, ttl_seconds=30):
        self.cache = {}
        self.ttl = ttl_seconds
        self.last_refresh = {}
        self.last_full_refresh = None
    
    def should_refresh(self, cloud_name=None):
        """Determina si debe refrescar los datos"""
        if cloud_name is None:
            if self.last_full_refresh is None:
                return True
            elapsed = (datetime.datetime.now() - self.last_full_refresh).total_seconds()
            return elapsed > self.ttl
        
        if cloud_name not in self.last_refresh:
            return True
        elapsed = (datetime.datetime.now() - self.last_refresh[cloud_name]).total_seconds()
        return elapsed > self.ttl
    
    def update_cache(self, cloud_name, data):
        """Actualiza la caché para una nube específica"""
        self.cache[cloud_name] = data
        self.last_refresh[cloud_name] = datetime.datetime.now()
    
    def update_full_cache(self, data):
        """Actualiza caché completa"""
        self.cache = data.copy()
        self.last_full_refresh = datetime.datetime.now()
    
    def get_cache(self, cloud_name):
        """Obtiene datos de caché"""
        return self.cache.get(cloud_name)
    
    def clear_cache(self):
        """Limpia toda la caché"""
        self.cache = {}
        self.last_refresh = {}
        self.last_full_refresh = None

cloud_cache = CloudCache(ttl_seconds=30)

# ==============================
# SISTEMA DE GESTIÓN DE ARCHIVOS TEMPORALES
# ==============================
class TempFileManager:
    """Gestiona archivos temporales y los elimina automáticamente"""
    def __init__(self):
        self.temp_files = []
        self.lock = threading.Lock()
    
    def register(self, filepath):
        """Registra un archivo temporal para limpieza automática"""
        with self.lock:
            self.temp_files.append(filepath)
    
    def cleanup(self, filepath=None):
        """Limpia archivos temporales"""
        with self.lock:
            if filepath:
                try:
                    if os.path.exists(filepath):
                        os.unlink(filepath)
                    if filepath in self.temp_files:
                        self.temp_files.remove(filepath)
                except Exception as e:
                    print(f"Error limpiando {filepath}: {e}")
            else:
                for f in self.temp_files[:]:
                    try:
                        if os.path.exists(f):
                            os.unlink(f)
                    except Exception as e:
                        print(f"Error limpiando {f}: {e}")
                self.temp_files.clear()
    
    def get_temp_path(self, original_name):
        """Genera una ruta temporal única"""
        timestamp = int(time.time() * 1000)
        random_id = random.randint(1000, 9999)
        safe_name = ''.join(c for c in original_name if c.isalnum() or c in '.-_').strip()
        if not safe_name:
            safe_name = f"archivo_{timestamp}"
        temp_path = f"/tmp/{timestamp}_{random_id}_{safe_name}"
        self.register(temp_path)
        return temp_path

# Instancia global
temp_manager = TempFileManager()

# ==============================
# SISTEMA DE ESTADÍSTICAS EN MEMORIA
# ==============================

class MemoryStats:
    """Sistema de estadísticas en memoria"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.reset_stats()
    
    def reset_stats(self):
        """Reinicia todas las estadísticas"""
        with self.lock:
            self.stats = {
                'total_uploads': 0,
                'total_deletes': 0,
                'total_size_uploaded': 0
            }
            self.user_stats = {}
            self.upload_logs = []
            self.delete_logs = []
    
    def log_upload(self, username, filename, file_size, moodle_host):
        """Registra una subida exitosa"""
        with self.lock:
            try:
                file_size = int(file_size)
            except:
                file_size = 0
            
            self.stats['total_uploads'] += 1
            self.stats['total_size_uploaded'] += file_size
            
            if username not in self.user_stats:
                self.user_stats[username] = {
                    'uploads': 0,
                    'deletes': 0,
                    'total_size': 0,
                    'last_activity': format_cuba_datetime()
                }
            
            self.user_stats[username]['uploads'] += 1
            self.user_stats[username]['total_size'] += file_size
            self.user_stats[username]['last_activity'] = format_cuba_datetime()
            
            log_entry = {
                'timestamp': format_cuba_datetime(),
                'username': username,
                'filename': filename,
                'file_size_bytes': file_size,
                'file_size_formatted': format_file_size(file_size),
                'moodle_host': moodle_host
            }
            self.upload_logs.append(log_entry)
            
            if len(self.upload_logs) > 300:
                self.upload_logs.pop(0)
            
            return True
    
    def log_delete(self, username, filename, evidence_name, moodle_host):
        """Registra una eliminación individual"""
        with self.lock:
            self.stats['total_deletes'] += 1
            
            if username not in self.user_stats:
                self.user_stats[username] = {
                    'uploads': 0,
                    'deletes': 0,
                    'total_size': 0,
                    'last_activity': format_cuba_datetime()
                }
            
            self.user_stats[username]['deletes'] += 1
            self.user_stats[username]['last_activity'] = format_cuba_datetime()
            
            log_entry = {
                'timestamp': format_cuba_datetime(),
                'username': username,
                'filename': filename,
                'evidence_name': evidence_name,
                'moodle_host': moodle_host,
                'type': 'delete'
            }
            self.delete_logs.append(log_entry)
            
            if len(self.delete_logs) > 300:
                self.delete_logs.pop(0)
            
            return True
    
    def log_delete_all(self, username, deleted_evidences, deleted_files, moodle_host):
        """Registra eliminación masiva"""
        with self.lock:
            self.stats['total_deletes'] += deleted_files
            
            if username not in self.user_stats:
                self.user_stats[username] = {
                    'uploads': 0,
                    'deletes': 0,
                    'total_size': 0,
                    'last_activity': format_cuba_datetime()
                }
            
            self.user_stats[username]['deletes'] += deleted_files
            self.user_stats[username]['last_activity'] = format_cuba_datetime()
            
            log_entry = {
                'timestamp': format_cuba_datetime(),
                'username': username,
                'action': 'delete_all',
                'deleted_evidences': deleted_evidences,
                'deleted_files': deleted_files,
                'moodle_host': moodle_host,
                'type': 'delete_all'
            }
            self.delete_logs.append(log_entry)
            
            if len(self.delete_logs) > 300:
                self.delete_logs.pop(0)
            
            return True
    
    def get_user_stats(self, username):
        """Obtiene estadísticas de un usuario"""
        with self.lock:
            return self.user_stats.get(username)
    
    def get_all_stats(self):
        """Obtiene todas las estadísticas globales"""
        with self.lock:
            return self.stats.copy()
    
    def get_all_users(self):
        """Obtiene todos los usuarios"""
        with self.lock:
            return self.user_stats.copy()
    
    def get_recent_uploads(self, limit=10):
        """Obtiene subidas recientes"""
        with self.lock:
            return self.upload_logs[-limit:][::-1] if self.upload_logs else []
    
    def get_recent_deletes(self, limit=10):
        """Obtiene eliminaciones recientes"""
        with self.lock:
            return self.delete_logs[-limit:][::-1] if self.delete_logs else []
    
    def has_any_data(self):
        """Verifica si hay datos"""
        with self.lock:
            return len(self.upload_logs) > 0 or len(self.delete_logs) > 0
    
    def clear_all_data(self):
        """Limpia todos los datos"""
        self.reset_stats()
        return "✅ Todos los datos han sido eliminados"

memory_stats = MemoryStats()

# ==============================
# FUNCIONES DE UTILIDAD
# ==============================

def get_cuba_time():
    if CUBA_TZ:
        return datetime.datetime.now(CUBA_TZ)
    return datetime.datetime.now()

def format_cuba_date(dt=None):
    if dt is None:
        dt = get_cuba_time()
    return dt.strftime("%d/%m/%y")

def format_cuba_datetime(dt=None):
    if dt is None:
        dt = get_cuba_time()
    return dt.strftime("%d/%m/%y %I:%M %p")

def format_file_size(size_bytes):
    """Formatea bytes a KB, MB o GB automáticamente"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def get_random_large_file_message():
    """Retorna un mensaje chistoso aleatorio para archivos grandes"""
    messages = [
        "¡Uy! Este archivo pesa más que mis ganas de trabajar los lunes 📦",
        "¿Seguro que no estás subiendo toda la temporada de tu serie favorita? 🎬",
        "Archivo detectado: XXL. Mi bandeja de entrada necesita hacer dieta 🍔",
        "¡500MB alert! Esto es más grande que mi capacidad de decisión en un restaurante 🍕",
        "Tu archivo necesita su propio código postal para viajar por internet 📮",
        "Vaya, con este peso hasta el bot necesita ir al gimnasio 💪",
        "¡Archivo XXL detectado! Preparando equipo de escalada para subirlo 🧗",
        "Este archivo es tan grande que necesita su propia habitación en la nube ☁️",
        "¿Esto es un archivo o un elefante digital disfrazado? 🐘",
        "¡Alerta de megabyte! Tu archivo podría tener su propia órbita 🛰️",
        "Archivo pesado detectado: activando modo grúa industrial 🏗️",
        "Este archivo hace que mi servidor sude bytes 💦",
        "¡Tamaño máximo superado! Necesitaré un café extra para esto ☕",
        "Tu archivo es más grande que mi lista de excusas para no hacer ejercicio 🏃",
        "Detectado: Archivo XXL. Preparando refuerzos estructurales 🏗️",
        "¡Vaya! Este archivo es tan grande que necesita pasaporte para viajar 🌍",
        "Con este peso, hasta la nube digital va a necesitar paraguas ☂️",
        "¡500MB detectados! ¿Traes la biblioteca de Alejandría en un ZIP? 📚",
        "Tu archivo tiene más MB que yo tengo neuronas después del café 🧠",
        "¡Alerta! Archivo de tamaño épico detectado. Activando modo Hulk 💚",
        "Este archivo es más pesado que mis remordimientos del lunes 🎭",
        "¡Uy! Con este tamaño hasta internet va a sudar la gota gorda 💧",
        "¿Seguro que no estás subiendo un elefante en formato MP4? 🐘📹",
        "Archivo XXL: Mi conexión acaba de pedir aumento de sueldo 💰",
        "¡500MB! Hasta los píxeles están haciendo dieta en este archivo 🥗"
    ]
    return random.choice(messages)

def expand_user_groups():
    """Convierte 'usuario1,usuario2':config a 'usuario1':config, 'usuario2':config"""
    expanded = {}
    for user_group, config in PRE_CONFIGURATED_USERS.items():
        users = [u.strip() for u in user_group.split(',')]
        for user in users:
            expanded[user] = config.copy()
    return expanded

def validate_user_access(username, bot, chat_id):
    """Valida si el usuario tiene acceso al bot"""
    jdb = JsonDatabase('database')
    jdb.check_create()
    jdb.load()
    
    expanded_users = expand_user_groups()
    if username not in expanded_users:
        bot.sendMessage(chat_id, '➲ No tienes acceso a este bot ✗')
        return None, None
    
    initialize_database(jdb)
    user_info = jdb.get_user(username)
    if user_info is None:
        config = expanded_users[username]
        jdb.create_user(username)
        user_info = jdb.get_user(username)
        for key, value in config.items():
            user_info[key] = value
        jdb.save_data_user(username, user_info)
        jdb.save()
    
    return jdb, user_info

def check_file_size(file_size, user_info, bot, message):
    """Verifica si el archivo excede el límite y muestra advertencia"""
    max_size = user_info.get('zips', 99) * 1024 * 1024
    file_size_mb = file_size / (1024 * 1024)
    
    if file_size > max_size:
        warning_msg = f"⚠️ {get_random_large_file_message()}\n\n"
        warning_msg += f"📏 Tamaño: {file_size_mb:.2f} MB\n"
        warning_msg += f"📦 Límite: {user_info.get('zips', 99)} MB\n"
        warning_msg += f"⬆️ Comprimiendo archivo..."
        bot.editMessageText(message, warning_msg)
        return True
    return False

def downloadFile(downloader,filename,currentBits,totalBits,speed,time,args):
    try:
        bot = args[0]
        message = args[1]
        thread = args[2]
        if thread.getStore('stop'):
            downloader.stop()
        downloadingInfo = infos.createDownloading(filename,totalBits,currentBits,speed,time,tid=thread.id)
        bot.editMessageText(message,downloadingInfo)
    except Exception as ex: 
        print(str(ex))

def uploadFile(filename,currentBits,totalBits,speed,time,args):
    try:
        bot = args[0]
        message = args[1]
        originalfile = args[2]
        thread = args[3]
        downloadingInfo = infos.createUploading(filename,totalBits,currentBits,speed,time,originalfile)
        bot.editMessageText(message,downloadingInfo)
    except Exception as ex: 
        print(str(ex))

def processUploadFiles(filename,filesize,files,update,bot,message,thread=None,jdb=None):
    try:
        bot.editMessageText(message,'⬆️ Preparando Para Subir ☁ ●●○')
        evidence = None
        fileid = None
        user_info = jdb.get_user(update.message.sender.username)
        proxy = ProxyCloud.parse(user_info['proxy'])
        
        client = MoodleClient(user_info['moodle_user'],
                              user_info['moodle_password'],
                              user_info['moodle_host'],
                              user_info['moodle_repo_id'],
                              proxy=proxy)
        loged = client.login()
        if loged:
            evidences = client.getEvidences()
            username = update.message.sender.username
            
            original_evidname = str(filename).split('.')[0]
            visible_evidname = original_evidname
            internal_evidname = f"{original_evidname}{USER_EVIDENCE_MARKER}{username}"
            
            for evid in evidences:
                if evid['name'] == internal_evidname:
                    evidence = evid
                    break
            if evidence is None:
                evidence = client.createEvidence(internal_evidname)

            originalfile = ''
            if len(files)>1:
                originalfile = filename
            draftlist = []
            for f in files:
                f_size = get_file_size(f)
                resp = None
                iter = 0
                tokenize = False
                if user_info['tokenize']!=0:
                   tokenize = True
                while resp is None:
                    fileid,resp = client.upload_file(f,evidence,fileid,progressfunc=uploadFile,args=(bot,message,originalfile,thread),tokenize=tokenize)
                    draftlist.append(resp)
                    iter += 1
                    if iter>=10:
                        break
                safe_delete_file(f)
            try:
                client.saveEvidence(evidence)
            except:
                pass
            return draftlist
        else:
            bot.editMessageText(message,'➥ Error En La Página ✗')
            return None
    except Exception as ex:
        bot.editMessageText(message,'➥ Error ✗\n' + str(ex))
        return None

def processFile(update,bot,message,file,thread=None,jdb=None):
    file_size = get_file_size(file)
    getUser = jdb.get_user(update.message.sender.username)
    max_file_size = 1024 * 1024 * getUser['zips']
    file_upload_count = 0
    client = None
    
    username = update.message.sender.username
    
    if file_size > max_file_size:
        compresingInfo = infos.createCompresing(file,file_size,max_file_size)
        bot.editMessageText(message,compresingInfo)
        zipname = str(file).split('.')[0] + createID()
        mult_file = zipfile.MultiFile(zipname,max_file_size)
        zip = zipfile.ZipFile(mult_file,  mode='w', compression=zipfile.ZIP_DEFLATED)
        zip.write(file)
        zip.close()
        mult_file.close()
        client = processUploadFiles(file,file_size,mult_file.files,update,bot,message,jdb=jdb)
        safe_delete_file(file)
        file_upload_count = len(mult_file.files)
    else:
        client = processUploadFiles(file,file_size,[file],update,bot,message,jdb=jdb)
        file_upload_count = 1
    
    visible_evidname = ''
    files = []
    if client:
        original_evidname = str(file).split('.')[0]
        visible_evidname = original_evidname
        internal_evidname = f"{original_evidname}{USER_EVIDENCE_MARKER}{username}"
        
        txtname = visible_evidname + '.txt'
        try:
            proxy = ProxyCloud.parse(getUser['proxy'])
            moodle_client = MoodleClient(getUser['moodle_user'],
                                         getUser['moodle_password'],
                                         getUser['moodle_host'],
                                         getUser['moodle_repo_id'],
                                         proxy=proxy)
            if moodle_client.login():
                evidences = moodle_client.getEvidences()
                
                evidence_index = -1
                for idx, ev in enumerate(evidences):
                    if ev['name'] == internal_evidname:
                        files = ev['files']
                        for i in range(len(files)):
                            url = files[i]['directurl']
                            if '?forcedownload=1' in url:
                                url = url.replace('?forcedownload=1', '')
                            elif '&forcedownload=1' in url:
                                url = url.replace('&forcedownload=1', '')
                            if '&token=' in url and '?' not in url:
                                url = url.replace('&token=', '?token=', 1)
                            files[i]['directurl'] = url
                        evidence_index = idx
                        break
                
                moodle_client.logout()
                
                findex = evidence_index if evidence_index != -1 else len(evidences) - 1
        except Exception as e:
            print(f"Error obteniendo índice de evidencia: {e}")
            findex = 0
        
        bot.deleteMessage(message.chat.id,message.message_id)
        finishInfo = infos.createFinishUploading(file,file_size,max_file_size,file_upload_count,file_upload_count,findex)
        filesInfo = infos.createFileMsg(file,files)
        bot.sendMessage(message.chat.id,finishInfo+'\n'+filesInfo,parse_mode='html')
        
        filename_clean = os.path.basename(file)
        memory_stats.log_upload(
            username=username,
            filename=filename_clean,
            file_size=file_size,
            moodle_host=getUser['moodle_host']
        )
        
        if len(files)>0:
            txtname = str(file).split('/')[-1].split('.')[0] + '.txt'
            sendTxt(txtname,files,update,bot)
    else:
        bot.editMessageText(message,'➥ Error en la página ✗')

def ddl(update,bot,message,url,file_name='',thread=None,jdb=None):
    downloader = Downloader()
    file = downloader.download_url(url,progressfunc=downloadFile,args=(bot,message,thread))
    if not downloader.stoping:
        if file:
            processFile(update,bot,message,file,jdb=jdb)
        else:
            try:
                bot.editMessageText(message,'➥ Error en la descarga ✗')
            except:
                bot.editMessageText(message,'➥ Error en la descarga ✗')

def sendTxt(name,files,update,bot):
    txt = open(name,'w')
    
    for i, f in enumerate(files):
        url = f['directurl']
        
        if '?forcedownload=1' in url:
            url = url.replace('?forcedownload=1', '')
        elif '&forcedownload=1' in url:
            url = url.replace('&forcedownload=1', '')
        
        if '&token=' in url and '?' not in url:
            url = url.replace('&token=', '?token=', 1)
        
        txt.write(url)
        
        if i < len(files) - 1:
            txt.write('\n\n')
    
    txt.close()
    bot.sendFile(update.message.chat.id,name)
    safe_delete_file(name)

def safe_delete_file(filepath):
    """Elimina un archivo de forma segura"""
    try:
        if os.path.exists(filepath):
            os.unlink(filepath)
            return True
    except Exception as e:
        print(f"Error eliminando {filepath}: {e}")
    return False

def initialize_database(jdb):
    expanded_users = expand_user_groups()
    database_updated = False
    
    for username, config in expanded_users.items():
        existing_user = jdb.get_user(username)
        
        if existing_user is None:
            jdb.create_user(username)
            user_data = jdb.get_user(username)
            for key, value in config.items():
                user_data[key] = value
            jdb.save_data_user(username, user_data)
            database_updated = True
    
    if database_updated:
        jdb.save()

def delete_message_after_delay(bot, chat_id, message_id, delay=8):
    """Elimina un mensaje después de un retraso específico"""
    def delete():
        time.sleep(delay)
        try:
            bot.deleteMessage(chat_id, message_id)
        except Exception as e:
            print(f"Error al eliminar mensaje: {e}")
    
    thread = threading.Thread(target=delete)
    thread.daemon = True
    thread.start()

def get_all_cloud_evidences_fast(use_cache=True):
    """
    Obtiene todas las evidencias de todas las nubes preconfiguradas
    """
    if use_cache and not cloud_cache.should_refresh():
        cached_data = cloud_cache.get_cache('all_clouds')
        if cached_data:
            return cached_data
    
    all_evidences = []
    
    for user_group, cloud_config in PRE_CONFIGURATED_USERS.items():
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        if use_cache and not cloud_cache.should_refresh(moodle_host):
            cached_evidence = cloud_cache.get_cache(moodle_host)
            if cached_evidence:
                all_evidences.extend(cached_evidence)
                continue
        
        try:
            proxy_parsed = ProxyCloud.parse(proxy)
            client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
            
            if client.login():
                evidences = client.getEvidences()
                
                for evidence in evidences:
                    evidence_info = {
                        'cloud_name': moodle_host,
                        'cloud_user': moodle_user,
                        'evidence_name': evidence.get('name', 'Sin nombre'),
                        'files_count': len(evidence.get('files', [])),
                        'evidence_data': evidence,
                        'group_users': user_group.split(','),
                        'cloud_config': cloud_config
                    }
                    all_evidences.append(evidence_info)
                
                client.logout()
                if use_cache:
                    cloud_cache.update_cache(moodle_host, [ev for ev in all_evidences if ev['cloud_name'] == moodle_host])
            else:
                print(f"No se pudo conectar a {moodle_host}")
                
        except Exception as e:
            print(f"Error obteniendo evidencias de {moodle_host}: {str(e)}")
    
    if use_cache:
        cloud_cache.update_full_cache(all_evidences)
    
    return all_evidences

def delete_evidence_from_cloud(cloud_config, evidence):
    """
    Elimina una evidencia específica de una nube
    """
    try:
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        proxy_parsed = ProxyCloud.parse(proxy)
        client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
        
        if client.login():
            all_evidences = client.getEvidences()
            evidence_to_delete = None
            
            for ev in all_evidences:
                if ev.get('id') == evidence.get('id'):
                    evidence_to_delete = ev
                    break
            
            if evidence_to_delete:
                evidence_name = evidence_to_delete.get('name', '')
                files_count = len(evidence_to_delete.get('files', []))
                client.deleteEvidence(evidence_to_delete)
                client.logout()
                cloud_cache.clear_cache()
                return True, evidence_name, files_count
            else:
                client.logout()
                return False, "", 0
        else:
            return False, "", 0
            
    except Exception as e:
        return False, f"Error: {str(e)}", 0

def delete_all_evidences_from_cloud(cloud_config):
    """
    Elimina todas las evidencias de una nube específica
    """
    try:
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        proxy_parsed = ProxyCloud.parse(proxy)
        client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
        
        if client.login():
            all_evidences = client.getEvidences()
            deleted_count = 0
            total_files = 0
            
            for evidence in all_evidences:
                try:
                    files_count = len(evidence.get('files', []))
                    client.deleteEvidence(evidence)
                    deleted_count += 1
                    total_files += files_count
                except:
                    pass
            
            client.logout()
            cloud_cache.clear_cache()
            return True, deleted_count, total_files
        else:
            return False, 0, 0
            
    except Exception as e:
        return False, 0, 0

class AdminEvidenceManager:
    """Gestor de evidencias para administrador"""
    
    def __init__(self):
        self.current_list = []
        self.clouds_dict = {}
        self.last_update = None
    
    def refresh_data(self, force=False):
        """Actualiza los datos de evidencias (con caché)"""
        if not force and not cloud_cache.should_refresh():
            return len(self.current_list)
        
        try:
            all_evidences = get_all_cloud_evidences_fast(use_cache=True)
            self.clouds_dict = {}
            
            for evidence in all_evidences:
                cloud_name = evidence['cloud_name']
                if cloud_name not in self.clouds_dict:
                    self.clouds_dict[cloud_name] = []
                self.clouds_dict[cloud_name].append(evidence)
            
            self.current_list = []
            cloud_index = 0
            for cloud_name, evidences in self.clouds_dict.items():
                for idx, evidence in enumerate(evidences):
                    self.current_list.append({
                        'cloud_idx': cloud_index,
                        'evid_idx': idx,
                        'cloud_name': cloud_name,
                        'evidence': evidence
                    })
            
            self.last_update = datetime.datetime.now()
            return len(self.current_list)
        except Exception as e:
            print(f"Error refrescando datos: {e}")
            return len(self.current_list)
    
    def get_evidence(self, cloud_idx, evid_idx):
        """Obtiene una evidencia específica"""
        try:
            if cloud_idx is None or evid_idx is None:
                return None
                
            if cloud_idx < len(self.clouds_dict):
                cloud_name = list(self.clouds_dict.keys())[cloud_idx]
                if evid_idx < len(self.clouds_dict[cloud_name]):
                    return self.clouds_dict[cloud_name][evid_idx]
        except Exception as e:
            print(f"Error obteniendo evidencia: {e}")
        return None
    
    def get_txt_for_evidence(self, cloud_idx, evid_idx):
        """Obtiene el TXT de una evidencia"""
        evidence = self.get_evidence(cloud_idx, evid_idx)
        if evidence:
            try:
                cloud_config = evidence['cloud_config']
                evidence_data = evidence['evidence_data']
                
                moodle_host = cloud_config.get('moodle_host', '')
                moodle_user = cloud_config.get('moodle_user', '')
                moodle_password = cloud_config.get('moodle_password', '')
                moodle_repo_id = cloud_config.get('moodle_repo_id', '')
                proxy = cloud_config.get('proxy', '')
                
                proxy_parsed = ProxyCloud.parse(proxy)
                client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
                
                if client.login():
                    all_evidences = client.getEvidences()
                    current_evidence = None
                    
                    for ev in all_evidences:
                        if ev.get('id') == evidence_data.get('id'):
                            current_evidence = ev
                            break
                    
                    if current_evidence:
                        files = current_evidence.get('files', [])
                        
                        for i in range(len(files)):
                            url = files[i]['directurl']
                            if '?forcedownload=1' in url:
                                url = url.replace('?forcedownload=1', '')
                            elif '&forcedownload=1' in url:
                                url = url.replace('&forcedownload=1', '')
                            if '&token=' in url and '?' not in url:
                                url = url.replace('&token=', '?token=', 1)
                            files[i]['directurl'] = url
                        
                        client.logout()
                        return files
                    client.logout()
            except Exception as e:
                print(f"Error obteniendo TXT: {e}")
        return None
    
    def clear_cache(self):
        """Limpia la caché del manager"""
        cloud_cache.clear_cache()
        self.current_list = []
        self.clouds_dict = {}
        self.last_update = None

admin_evidence_manager = AdminEvidenceManager()

def extract_one_param_simple(msgText, prefix):
    """
    Extrae un parámetro de forma simple usando split
    """
    try:
        if prefix in msgText:
            parts = msgText.split('_')
            if prefix == '/adm_cloud_':
                return int(parts[2]) if len(parts) > 2 else None
            elif prefix == '/adm_wipe_':
                return int(parts[2]) if len(parts) > 2 else None
    except (ValueError, IndexError):
        return None
    return None

def extract_two_params_simple(msgText, prefix):
    """
    Extrae dos parámetros de forma simple usando split
    """
    try:
        if prefix in msgText:
            parts = msgText.split('_')
            if len(parts) > 3:
                param1 = int(parts[2])
                param2 = int(parts[3])
                return [param1, param2]
    except (ValueError, IndexError):
        return None
    return None

def show_updated_cloud(bot, message, cloud_idx):
    """Muestra la lista actualizada de una nube después de eliminar"""
    try:
        admin_evidence_manager.refresh_data(force=True)
        cloud_names = list(admin_evidence_manager.clouds_dict.keys())
        
        if cloud_idx < 0 or cloud_idx >= len(cloud_names):
            show_updated_all_clouds(bot, message)
            return
        
        cloud_name = cloud_names[cloud_idx]
        evidences = admin_evidence_manager.clouds_dict.get(cloud_name, [])
        
        if not evidences:
            short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
            empty_msg = f"""
📭 NUBE VACÍA
━━━━━━━━━━━━━━━━━━━

✅ ELIMINACIÓN COMPLETA
☁️ {short_name}

🎉 ¡Has eliminado todas las evidencias de esta nube!

🔄 Regresando a todas las nubes...
━━━━━━━━━━━━━━━━━━━
            """
            bot.editMessageText(message, empty_msg)
            time.sleep(1.5)
            show_updated_all_clouds(bot, message)
            return
        
        short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
        
        list_msg = f"""
📋 NUBE ACTUALIZADA
☁️ {short_name}
━━━━━━━━━━━━━━━━━━━

"""
        for idx, evidence in enumerate(evidences):
            ev_name = evidence['evidence_name']
            
            clean_name = ev_name
            user_tags = []
            
            for user in evidence['group_users']:
                marker = f"{USER_EVIDENCE_MARKER}{user}"
                if marker in ev_name:
                    clean_name = ev_name.replace(marker, "").strip()
                    user_tags.append(f"@{user}")
            
            if user_tags:
                user_str = f" ({', '.join(user_tags[:2])})"
                if len(user_tags) > 2:
                    user_str = f" ({', '.join(user_tags[:2])}...)"
            else:
                user_str = ""
            
            list_msg += f"{idx}. {clean_name[:35]}"
            if len(clean_name) > 35:
                list_msg += "..."
            list_msg += f"{user_str}\n"
            list_msg += f"   📁 {evidence['files_count']} archivos\n"
            list_msg += f"   👁️ /adm_show_{cloud_idx}_{idx}\n"
            list_msg += f"   📄 /adm_fetch_{cloud_idx}_{idx}\n"
            list_msg += f"   🗑️ /adm_delete_{cloud_idx}_{idx}\n\n"
        
        total_evidences = len(evidences)
        total_files = sum(e['files_count'] for e in evidences)
        
        list_msg += f"""
━━━━━━━━━━━━━━━━━━━
🔧 ACCIONES MASIVAS:
/adm_wipe_{cloud_idx} - Eliminar TODO de esta nube

📊 RESUMEN:
• Evidencias: {total_evidences}
• Archivos: {total_files}
━━━━━━━━━━━━━━━━━━━
        """
        
        bot.editMessageText(message, list_msg)
        
    except Exception as e:
        error_msg = f"""
❌ ERROR AL ACTUALIZAR
━━━━━━━━━━━━━━━━━━━

⚠️ No se pudo mostrar la nube actualizada.

🔧 Solución:
Usa /adm_allclouds para ver todas las nubes disponibles

━━━━━━━━━━━━━━━━━━━
        """
        bot.editMessageText(message, error_msg)

def show_updated_all_clouds(bot, message):
    """Muestra todas las nubes actualizadas después de una eliminación masiva"""
    try:
        admin_evidence_manager.refresh_data()
        
        total_evidences = len(admin_evidence_manager.current_list)
        total_clouds = len(admin_evidence_manager.clouds_dict)
        total_files = 0
        
        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
            for ev in evidences:
                total_files += ev['files_count']
        
        if total_evidences == 0:
            empty_msg = f"""
👑 TODAS LAS NUBES ACTUALIZADAS
━━━━━━━━━━━━━━━━━━━

📊 RESUMEN GENERAL:
• Nubes: {total_clouds}
• Evidencias totales: 0
• Archivos totales: 0

━━━━━━━━━━━━━━━━━━━
✅ Todas las nubes están vacías
📭 No hay evidencias para eliminar
━━━━━━━━━━━━━━━━━━━
            """
            bot.editMessageText(message, empty_msg)
            return
        
        menu_msg = f"""
👑 TODAS LAS NUBES ACTUALIZADAS
━━━━━━━━━━━━━━━━━━━

📊 RESUMEN GENERAL:
• Nubes: {total_clouds}
• Evidencias totales: {total_evidences}
• Archivos totales: {total_files}

📋 NUBES DISPONIBLES:"""
        
        cloud_index = 0
        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
            cloud_files = sum(ev['files_count'] for ev in evidences)
            short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
            
            menu_msg += f"\n\n{cloud_index}. {short_name}"
            menu_msg += f"\n   📁 {len(evidences)} evidencias, {cloud_files} archivos"
            menu_msg += f"\n   🔍 /adm_cloud_{cloud_index}"
            
            if len(evidences) > 0:
                menu_msg += f"\n   🗑️ /adm_wipe_{cloud_index}"
            
            cloud_index += 1
        
        if total_evidences > 0:
            menu_msg += f"""

━━━━━━━━━━━━━━━━━━━
🔧 OPCIONES MASIVAS:
/adm_nuke - ⚠️ Eliminar TODO (peligro)
━━━━━━━━━━━━━━━━━━━
        """
        
        bot.editMessageText(message, menu_msg)
        
    except Exception as e:
        bot.editMessageText(message, f'❌ Error al mostrar nubes actualizadas: {str(e)}')

def show_loading_progress(bot, message, step, total_steps=3):
    """Muestra una barra de progreso para operaciones largas"""
    progress_chars = ['○', '◔', '◑', '◕', '●']
    progress = int((step / total_steps) * 4)
    bar = progress_chars[progress] if progress < len(progress_chars) else progress_chars[-1]
    
    loading_msgs = [
        "🔄 Conectando con las nubes...",
        "📊 Procesando datos...",
        "✅ Actualizando información..."
    ]
    
    msg = loading_msgs[step-1] if step <= len(loading_msgs) else f"Procesando... ({step}/{total_steps})"
    bot.editMessageText(message, f"{msg} {bar}")

def process_downloaded_file(update, bot, message, file_data, file_name, file_size, thread, jdb, user_info):
    """Procesa un archivo ya descargado (código común para todos los métodos)"""
    try:
        check_file_size(file_size, user_info, bot, message)
        
        temp_path = temp_manager.get_temp_path(file_name)
        with open(temp_path, 'wb') as f:
            f.write(file_data)
        
        processFile(update, bot, message, temp_path, thread=thread, jdb=jdb)
        
        temp_manager.cleanup(temp_path)
        
    except Exception as e:
        bot.editMessageText(message, f'❌ Error procesando archivo: {str(e)}')
        temp_manager.cleanup()
        return False
    
    return True

# ==============================
# MANEJADORES DE ARCHIVOS DIRECTOS (NUEVOS)
# ==============================

def ondocument(update, bot: ObigramClient):
    """Maneja cuando el usuario envía un ARCHIVO INDIVIDUAL"""
    try:
        thread = bot.this_thread
        username = update.message.sender.username
        
        jdb, user_info = validate_user_access(username, bot, update.message.chat.id)
        if not jdb:
            return
        
        doc = update.message.document
        file_id = doc.file_id
        file_name = doc.file_name or f"archivo_{int(time.time())}.bin"
        file_size = doc.file_size or 0
        
        if file_size > 2 * 1024 * 1024 * 1024:
            bot.sendMessage(update.message.chat.id, '❌ Archivo demasiado grande (máximo 2GB)')
            return
        
        message = bot.sendMessage(
            update.message.chat.id,
            f'📥 **ARCHIVO RECIBIDO**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'📄 **Nombre:** `{file_name}`\n'
            f'📏 **Tamaño:** {format_file_size(file_size)}\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'⬇️ Descargando de Telegram...'
        )
        
        bot.editMessageText(message, '⬇️ Descargando... 25%')
        file_data = bot.downloadFile(file_id)
        
        if file_data:
            bot.editMessageText(message, '⬇️ Descargado. Procesando... 100%')
            process_downloaded_file(update, bot, message, file_data, file_name, file_size, thread, jdb, user_info)
        else:
            bot.editMessageText(message, '❌ Error al descargar el archivo de Telegram')
            
    except Exception as ex:
        print(f"Error en ondocument: {str(ex)}")
        traceback.print_exc()
        try:
            bot.sendMessage(update.message.chat.id, f'❌ Error: {str(ex)}')
        except:
            pass

def onalbum(update, bot: ObigramClient):
    """Maneja cuando el usuario envía MÚLTIPLES ARCHIVOS"""
    try:
        thread = bot.this_thread
        username = update.message.sender.username
        
        jdb, user_info = validate_user_access(username, bot, update.message.chat.id)
        if not jdb:
            return
        
        media_group = update.message.media_group
        total_files = len(media_group)
        
        message = bot.sendMessage(
            update.message.chat.id,
            f'📦 **MÚLTIPLES ARCHIVOS**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'📊 **Total:** {total_files} archivos\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'⬇️ Procesando... 0/{total_files}'
        )
        
        successful = 0
        failed = 0
        
        for idx, media in enumerate(media_group, 1):
            try:
                bot.editMessageText(
                    message,
                    f'📦 **PROCESANDO**\n'
                    f'━━━━━━━━━━━━━━━━━━━\n'
                    f'📊 **Progreso:** {idx}/{total_files}\n'
                    f'━━━━━━━━━━━━━━━━━━━\n'
                    f'⬇️ Archivo {idx}...'
                )
                
                if media.document:
                    doc = media.document
                    file_id = doc.file_id
                    file_name = doc.file_name or f"archivo_{idx}.bin"
                    file_size = doc.file_size or 0
                elif media.photo:
                    photo = media.photo[-1]
                    file_id = photo.file_id
                    file_name = f"foto_{idx}.jpg"
                    file_size = photo.file_size or 0
                elif media.video:
                    video = media.video
                    file_id = video.file_id
                    file_name = video.file_name or f"video_{idx}.mp4"
                    file_size = video.file_size or 0
                else:
                    failed += 1
                    continue
                
                file_data = bot.downloadFile(file_id)
                
                if file_data:
                    temp_path = temp_manager.get_temp_path(file_name)
                    with open(temp_path, 'wb') as f:
                        f.write(file_data)
                    
                    processFile(update, bot, message, temp_path, thread=thread, jdb=jdb)
                    successful += 1
                else:
                    failed += 1
                
            except Exception as e:
                print(f"Error procesando archivo {idx}: {e}")
                failed += 1
        
        final_msg = f"""
📦 **PROCESAMIENTO COMPLETADO**
━━━━━━━━━━━━━━━━━━━
✅ **Exitosos:** {successful}
❌ **Fallidos:** {failed}
📊 **Total:** {total_files}
━━━━━━━━━━━━━━━━━━━
        """
        
        bot.editMessageText(message, final_msg)
        
    except Exception as ex:
        print(f"Error en onalbum: {str(ex)}")
        traceback.print_exc()
        try:
            bot.sendMessage(update.message.chat.id, f'❌ Error: {str(ex)}')
        except:
            pass

def onphoto(update, bot: ObigramClient):
    """Maneja cuando el usuario envía una FOTO"""
    try:
        thread = bot.this_thread
        username = update.message.sender.username
        
        jdb, user_info = validate_user_access(username, bot, update.message.chat.id)
        if not jdb:
            return
        
        photo = update.message.photo[-1]
        file_id = photo.file_id
        file_size = photo.file_size or 0
        file_name = f"foto_{int(time.time())}.jpg"
        
        message = bot.sendMessage(
            update.message.chat.id,
            f'🖼️ **FOTO RECIBIDA**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'📏 **Tamaño:** {format_file_size(file_size)}\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'⬇️ Procesando...'
        )
        
        file_data = bot.downloadFile(file_id)
        
        if file_data:
            process_downloaded_file(update, bot, message, file_data, file_name, file_size, thread, jdb, user_info)
        else:
            bot.editMessageText(message, '❌ Error al descargar la foto')
            
    except Exception as ex:
        print(f"Error en onphoto: {str(ex)}")
        traceback.print_exc()

def onvideo(update, bot: ObigramClient):
    """Maneja cuando el usuario envía un VIDEO"""
    try:
        thread = bot.this_thread
        username = update.message.sender.username
        
        jdb, user_info = validate_user_access(username, bot, update.message.chat.id)
        if not jdb:
            return
        
        video = update.message.video
        file_id = video.file_id
        file_name = video.file_name or f"video_{int(time.time())}.mp4"
        file_size = video.file_size or 0
        
        message = bot.sendMessage(
            update.message.chat.id,
            f'🎬 **VIDEO RECIBIDO**\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'📄 **Nombre:** `{file_name}`\n'
            f'📏 **Tamaño:** {format_file_size(file_size)}\n'
            f'━━━━━━━━━━━━━━━━━━━\n'
            f'⬇️ Procesando...'
        )
        
        file_data = bot.downloadFile(file_id)
        
        if file_data:
            process_downloaded_file(update, bot, message, file_data, file_name, file_size, thread, jdb, user_info)
        else:
            bot.editMessageText(message, '❌ Error al descargar el video')
            
    except Exception as ex:
        print(f"Error en onvideo: {str(ex)}")
        traceback.print_exc()

# ==============================
# FUNCIÓN PRINCIPAL ONMESSAGE
# ==============================

def onmessage(update,bot:ObigramClient):
    try:
        thread = bot.this_thread
        username = update.message.sender.username

        jdb = JsonDatabase('database')
        jdb.check_create()
        jdb.load()
        
        expanded_users = expand_user_groups()
        
        if username not in expanded_users:
            bot.sendMessage(update.message.chat.id,'➲ No tienes acceso a este bot ✗')
            return
        
        initialize_database(jdb)
        
        user_info = jdb.get_user(username)
        if user_info is None:
            config = expanded_users[username]
            jdb.create_user(username)
            user_info = jdb.get_user(username)
            for key, value in config.items():
                user_info[key] = value
            jdb.save_data_user(username, user_info)
            jdb.save()

        msgText = ''
        try: 
            msgText = update.message.text
        except:
            pass

        if '/cancel_' in msgText:
            try:
                cmd = str(msgText).split('_',2)
                tid = cmd[1]
                tcancel = bot.threads[tid]
                msg = tcancel.getStore('msg')
                tcancel.store('stop',True)
                time.sleep(3)
                bot.editMessageText(msg,'➲ Tarea Cancelada ✗ ')
            except Exception as ex:
                print(str(ex))
            return

        message = bot.sendMessage(update.message.chat.id,'➲ Procesando ✪ ●●○')
        thread.store('msg',message)

        # COMANDO /start
        if '/start' in msgText:
            if username == ADMIN_USERNAME:
                start_msg = f"""
👑 **USUARIO ADMINISTRADOR**

👤 Usuario: @{username}
🔧 Rol: Administrador

📤 **SUBIR ARCHIVOS:**
• Envía un **enlace directo** (URL)
• Envía **archivos adjuntos**
• Envía **fotos** o **videos**
• Envía **múltiples archivos**

📁 **TUS COMANDOS:**
/files - Ver tus evidencias
/txt_X - Obtener TXT de evidencia
/del_X - Eliminar evidencia
/delall - Eliminar todas
/mystats - Tus estadísticas

👑 **COMANDOS ADMIN:**
/admin - Panel de administración
/adm_logs - Ver logs del sistema
/adm_users - Ver estadísticas
/adm_allclouds - Gestionar nubes

━━━━━━━━━━━━━━━━━━━
🔗 FileToLink: @fileeliellinkBot
                """
            else:
                start_msg = f"""
👤 **USUARIO REGULAR**

👤 Usuario: @{username}
☁️ Nube: {user_info['moodle_host']}

📤 **SUBIR ARCHIVOS:**
• Envía un **enlace directo** (URL)
• Envía **archivos adjuntos**
• Envía **fotos** o **videos**
• Envía **múltiples archivos**

📁 **TUS COMANDOS:**
/files - Ver tus evidencias
/txt_X - Obtener TXT de evidencia
/del_X - Eliminar evidencia
/delall - Eliminar todas
/mystats - Tus estadísticas

━━━━━━━━━━━━━━━━━━━
🔗 FileToLink: @fileeliellinkBot
                """
            
            bot.editMessageText(message, start_msg)
            return

        # COMANDOS DE ADMINISTRADOR
        if username == ADMIN_USERNAME:
            if msgText == '/admin':
                stats = memory_stats.get_all_stats()
                total_size_formatted = format_file_size(stats['total_size_uploaded'])
                current_date = format_cuba_date()
                
                admin_msg = f"""
👑 **PANEL DE ADMINISTRADOR**
📅 {current_date}
━━━━━━━━━━━━━━━━━━━
📊 **ESTADÍSTICAS GLOBALES:**
• Subidas totales: {stats['total_uploads']}
• Eliminaciones totales: {stats['total_deletes']}
• Espacio total subido: {total_size_formatted}
• Nubes configuradas: {len(PRE_CONFIGURATED_USERS)}

📈 **COMANDOS:**
/adm_logs - Ver últimos logs
/adm_users - Ver estadísticas por usuario
/adm_uploads - Ver últimas subidas
/adm_deletes - Ver últimas eliminaciones

☁️ **GESTIÓN DE NUBES:**
/adm_allclouds - Ver todas las nubes
/adm_cloud_X - Ver nube específica
/adm_delete_X_Y - Eliminar evidencia
/adm_wipe_X - Limpiar toda una nube

━━━━━━━━━━━━━━━━━━━
🕐 Hora Cuba: {format_cuba_datetime()}
                """
                
                bot.editMessageText(message, admin_msg)
                return
            
            elif '/adm_allclouds' in msgText:
                try:
                    show_loading_progress(bot, message, 1, 3)
                    total_evidences = admin_evidence_manager.refresh_data()
                    show_loading_progress(bot, message, 2, 3)
                    
                    if total_evidences == 0:
                        empty_msg = f"""
👑 **TODAS LAS NUBES**
━━━━━━━━━━━━━━━━━━━

📊 **RESUMEN GENERAL:**
• Nubes configuradas: {len(PRE_CONFIGURATED_USERS)}
• Evidencias totales: 0
• Archivos totales: 0

━━━━━━━━━━━━━━━━━━━
✅ Todas las nubes están vacías
📭 No hay evidencias para eliminar
━━━━━━━━━━━━━━━━━━━
                        """
                        bot.editMessageText(message, empty_msg)
                        return
                    
                    total_clouds = len(admin_evidence_manager.clouds_dict)
                    total_files = 0
                    
                    for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                        for ev in evidences:
                            total_files += ev['files_count']
                    
                    menu_msg = f"""
👑 **GESTIÓN DE TODAS LAS NUBES**
━━━━━━━━━━━━━━━━━━━

📊 **RESUMEN GENERAL:**
• Nubes: {total_clouds}
• Evidencias totales: {total_evidences}
• Archivos totales: {total_files}

📋 **NUBES DISPONIBLES:**"""
                    
                    cloud_index = 0
                    for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                        cloud_files = sum(ev['files_count'] for ev in evidences)
                        short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                        
                        menu_msg += f"\n\n{cloud_index}. {short_name}"
                        menu_msg += f"\n   📁 {len(evidences)} evidencias, {cloud_files} archivos"
                        menu_msg += f"\n   🔍 /adm_cloud_{cloud_index}"
                        
                        if len(evidences) > 0:
                            menu_msg += f"\n   🗑️ /adm_wipe_{cloud_index}"
                        
                        cloud_index += 1
                    
                    show_loading_progress(bot, message, 3, 3)
                    
                    if total_evidences > 0:
                        menu_msg += f"""

━━━━━━━━━━━━━━━━━━━
🔧 **OPCIONES MASIVAS:**
/adm_nuke - ⚠️ Eliminar TODO (peligro)
━━━━━━━━━━━━━━━━━━━
                        """
                    
                    bot.editMessageText(message, menu_msg)
                    
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_cloud_' in msgText:
                try:
                    cloud_idx = extract_one_param_simple(msgText, '/adm_cloud_')
                    if cloud_idx is None:
                        bot.editMessageText(message, '❌ Formato incorrecto. Use: /adm_cloud_0')
                        return
                    
                    admin_evidence_manager.refresh_data()
                    
                    if cloud_idx < 0 or cloud_idx >= len(admin_evidence_manager.clouds_dict):
                        bot.editMessageText(message, f'❌ Índice inválido. Máximo: {len(admin_evidence_manager.clouds_dict)-1}')
                        return
                    
                    cloud_name = list(admin_evidence_manager.clouds_dict.keys())[cloud_idx]
                    evidences = admin_evidence_manager.clouds_dict[cloud_name]
                    
                    short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                    
                    if not evidences:
                        empty_msg = f"""
📭 **NUBE VACÍA**
━━━━━━━━━━━━━━━━━━━

☁️ {short_name}
📊 No hay evidencias en esta nube.

🔍 Usa /adm_allclouds para ver otras nubes
━━━━━━━━━━━━━━━━━━━
                        """
                        bot.editMessageText(message, empty_msg)
                        return
                    
                    list_msg = f"""
📋 **EVIDENCIAS DE LA NUBE**
☁️ {short_name}
━━━━━━━━━━━━━━━━━━━

"""
                    for idx, evidence in enumerate(evidences):
                        ev_name = evidence['evidence_name']
                        
                        clean_name = ev_name
                        user_tags = []
                        
                        for user in evidence['group_users']:
                            marker = f"{USER_EVIDENCE_MARKER}{user}"
                            if marker in ev_name:
                                clean_name = ev_name.replace(marker, "").strip()
                                user_tags.append(f"@{user}")
                        
                        if user_tags:
                            user_str = f" ({', '.join(user_tags[:2])})"
                            if len(user_tags) > 2:
                                user_str = f" ({', '.join(user_tags[:2])}...)"
                        else:
                            user_str = ""
                        
                        list_msg += f"{idx}. {clean_name[:35]}"
                        if len(clean_name) > 35:
                            list_msg += "..."
                        list_msg += f"{user_str}\n"
                        list_msg += f"   📁 {evidence['files_count']} archivos\n"
                        list_msg += f"   👁️ /adm_show_{cloud_idx}_{idx}\n"
                        list_msg += f"   📄 /adm_fetch_{cloud_idx}_{idx}\n"
                        list_msg += f"   🗑️ /adm_delete_{cloud_idx}_{idx}\n\n"
                    
                    total_evidences = len(evidences)
                    total_files = sum(e['files_count'] for e in evidences)
                    
                    list_msg += f"""
━━━━━━━━━━━━━━━━━━━
🔧 **ACCIONES MASIVAS:**
/adm_wipe_{cloud_idx} - Eliminar TODO de esta nube

📊 **RESUMEN:**
• Evidencias: {total_evidences}
• Archivos: {total_files}
━━━━━━━━━━━━━━━━━━━
                    """
                    
                    bot.editMessageText(message, list_msg)
                    
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_show_' in msgText:
                try:
                    params = extract_two_params_simple(msgText, '/adm_show_')
                    if params is None:
                        bot.editMessageText(message, '❌ Formato incorrecto. Use: /adm_show_0_1')
                        return
                    
                    cloud_idx, evid_idx = params
                    
                    evidence = admin_evidence_manager.get_evidence(cloud_idx, evid_idx)
                    if evidence:
                        ev_name = evidence['evidence_name']
                        cloud_name = evidence['cloud_name']
                        short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                        
                        clean_name = ev_name
                        for user in evidence['group_users']:
                            marker = f"{USER_EVIDENCE_MARKER}{user}"
                            if marker in ev_name:
                                clean_name = ev_name.replace(marker, "").strip()
                                break
                        
                        show_msg = f"""
👁️ **DETALLES DE EVIDENCIA**
━━━━━━━━━━━━━━━━━━━

📝 **Nombre:** {clean_name}
📁 **Archivos:** {evidence['files_count']}
☁️ **Nube:** {short_name}

🔧 **ACCIONES:**
📄 /adm_fetch_{cloud_idx}_{evid_idx} - Descargar TXT
🗑️ /adm_delete_{cloud_idx}_{evid_idx} - Eliminar

📊 **ESTADÍSTICAS:**
• Nube índice: {cloud_idx}
• Evidencia índice: {evid_idx}
━━━━━━━━━━━━━━━━━━━
                        """
                        
                        bot.editMessageText(message, show_msg)
                    else:
                        bot.editMessageText(message, '❌ No se encontró la evidencia')
                        
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_fetch_' in msgText:
                try:
                    params = extract_two_params_simple(msgText, '/adm_fetch_')
                    if params is None:
                        bot.editMessageText(message, '❌ Formato incorrecto. Use: /adm_fetch_0_1')
                        return
                    
                    cloud_idx, evid_idx = params
                    
                    bot.editMessageText(message, '📄 Obteniendo archivo TXT...')
                    
                    files = admin_evidence_manager.get_txt_for_evidence(cloud_idx, evid_idx)
                    
                    if files:
                        evidence = admin_evidence_manager.get_evidence(cloud_idx, evid_idx)
                        if evidence:
                            ev_name = evidence['evidence_name']
                            clean_name = ev_name
                            
                            for user in evidence['group_users']:
                                marker = f"{USER_EVIDENCE_MARKER}{user}"
                                if marker in ev_name:
                                    clean_name = ev_name.replace(marker, "").strip()
                                    break
                            
                            safe_name = ''.join(c for c in clean_name if c.isalnum() or c in (' ', '-', '_')).strip()
                            if not safe_name:
                                safe_name = f"evidencia_{cloud_idx}_{evid_idx}"
                            
                            txtname = f"{safe_name}.txt"
                            txt = open(txtname, 'w')
                            
                            for i, f in enumerate(files):
                                url = f['directurl']
                                txt.write(url)
                                if i < len(files) - 1:
                                    txt.write('\n\n')
                            
                            txt.close()
                            bot.sendFile(update.message.chat.id, txtname)
                            safe_delete_file(txtname)
                            
                            bot.editMessageText(message, f'✅ TXT enviado: {clean_name[:50]}')
                        else:
                            bot.editMessageText(message, '❌ No se encontró la evidencia')
                    else:
                        bot.editMessageText(message, '❌ No hay archivos en esta evidencia')
                        
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_delete_' in msgText:
                try:
                    params = extract_two_params_simple(msgText, '/adm_delete_')
                    if params is None:
                        bot.editMessageText(message, '❌ Formato incorrecto. Use: /adm_delete_0_1')
                        return
                    
                    cloud_idx, evid_idx = params
                    
                    bot.editMessageText(message, '🔍 Verificando datos...')
                    
                    admin_evidence_manager.refresh_data()
                    cloud_names = list(admin_evidence_manager.clouds_dict.keys())
                    
                    if cloud_idx < 0 or cloud_idx >= len(cloud_names):
                        bot.editMessageText(message, f'❌ Índice de nube inválido')
                        show_updated_all_clouds(bot, message)
                        return
                    
                    cloud_name = cloud_names[cloud_idx]
                    evidences = admin_evidence_manager.clouds_dict.get(cloud_name, [])
                    
                    if not evidences:
                        bot.editMessageText(message, f'📭 La nube {cloud_idx} ya está vacía')
                        show_updated_all_clouds(bot, message)
                        return
                    
                    if evid_idx < 0 or evid_idx >= len(evidences):
                        bot.editMessageText(message, f'❌ Índice de evidencia inválido')
                        return
                    
                    evidence = evidences[evid_idx]
                    
                    ev_name = evidence['evidence_name']
                    clean_name = ev_name
                    for user in evidence['group_users']:
                        marker = f"{USER_EVIDENCE_MARKER}{user}"
                        if marker in ev_name:
                            clean_name = ev_name.replace(marker, "").strip()
                            break
                    
                    short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                    
                    bot.editMessageText(message, f'🗑️ Eliminando evidencia: {clean_name[:50]}...')
                    
                    success, ev_name, files_count = delete_evidence_from_cloud(
                        evidence['cloud_config'], 
                        evidence['evidence_data']
                    )
                    
                    if success:
                        admin_evidence_manager.refresh_data(force=True)
                        
                        cloud_names = list(admin_evidence_manager.clouds_dict.keys())
                        
                        if cloud_idx < len(cloud_names):
                            current_evidences = admin_evidence_manager.clouds_dict.get(cloud_names[cloud_idx], [])
                            
                            if current_evidences:
                                result_msg = f"""
✅ **ELIMINACIÓN EXITOSA**
━━━━━━━━━━━━━━━━━━━

🗑️ **Evidencia:** {clean_name[:50]}
{'...' if len(clean_name) > 50 else ''}
📁 **Archivos eliminados:** {files_count}
☁️ **Nube:** {short_name}

🔄 Mostrando nube actualizada...
━━━━━━━━━━━━━━━━━━━
                                """
                                bot.editMessageText(message, result_msg)
                                time.sleep(1)
                                show_updated_cloud(bot, message, cloud_idx)
                            else:
                                result_msg = f"""
✅ **ELIMINACIÓN COMPLETA**
━━━━━━━━━━━━━━━━━━━

🗑️ Última evidencia eliminada de esta nube
📁 **Archivos borrados:** {files_count}

🔄 Mostrando todas las nubes...
━━━━━━━━━━━━━━━━━━━
                                """
                                bot.editMessageText(message, result_msg)
                                time.sleep(1)
                                show_updated_all_clouds(bot, message)
                        else:
                            show_updated_all_clouds(bot, message)
                    else:
                        bot.editMessageText(message, f'❌ Error al eliminar: {clean_name}')
                        
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_wipe_' in msgText:
                try:
                    cloud_idx = extract_one_param_simple(msgText, '/adm_wipe_')
                    if cloud_idx is None:
                        bot.editMessageText(message, '❌ Formato incorrecto. Use: /adm_wipe_0')
                        return
                    
                    if cloud_idx < 0 or cloud_idx >= len(admin_evidence_manager.clouds_dict):
                        bot.editMessageText(message, f'❌ Índice inválido. Máximo: {len(admin_evidence_manager.clouds_dict)-1}')
                        return
                    
                    cloud_name = list(admin_evidence_manager.clouds_dict.keys())[cloud_idx]
                    evidences = admin_evidence_manager.clouds_dict[cloud_name]
                    
                    if not evidences:
                        bot.editMessageText(message, f'📭 La nube {cloud_idx} ya está vacía')
                        return
                    
                    total_evidences = len(evidences)
                    total_files = sum(e['files_count'] for e in evidences)
                    short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                    
                    bot.editMessageText(message, f'💣 Limpiando nube {short_name}...')
                    
                    cloud_config = None
                    for user_group, config in PRE_CONFIGURATED_USERS.items():
                        if config.get('moodle_host') == cloud_name:
                            cloud_config = config
                            break
                    
                    if cloud_config:
                        success, deleted_count, total_files = delete_all_evidences_from_cloud(cloud_config)
                        
                        if success:
                            admin_evidence_manager.refresh_data(force=True)
                            
                            result_msg = f"""
💥 **LIMPIEZA COMPLETA EXITOSA**
━━━━━━━━━━━━━━━━━━━

✅ **Nube:** {short_name}
✅ **Evidencias eliminadas:** {deleted_count}
✅ **Archivos borrados:** {total_files}

🔄 Mostrando todas las nubes...
━━━━━━━━━━━━━━━━━━━
                            """
                            
                            bot.editMessageText(message, result_msg)
                            time.sleep(1)
                            
                            show_updated_all_clouds(bot, message)
                        else:
                            bot.editMessageText(message, f'❌ Error al limpiar la nube {short_name}')
                    else:
                        bot.editMessageText(message, '❌ No se encontró configuración para esta nube')
                        
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_nuke' in msgText:
                try:
                    total_clouds = len(admin_evidence_manager.clouds_dict)
                    total_evidences = len(admin_evidence_manager.current_list)
                    total_files = 0
                    
                    for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                        for ev in evidences:
                            total_files += ev['files_count']
                    
                    if total_evidences == 0:
                        bot.editMessageText(message, '📭 No hay evidencias para eliminar')
                        return
                    
                    bot.editMessageText(message, '💣💣💣 **ELIMINANDO TODO DE TODAS LAS NUBES**...')
                    
                    results = []
                    deleted_total = 0
                    files_total = 0
                    
                    for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
                        cloud_config = None
                        for user_group, config in PRE_CONFIGURATED_USERS.items():
                            if config.get('moodle_host') == cloud_name:
                                cloud_config = config
                                break
                        
                        if cloud_config:
                            success, deleted_count, total_files = delete_all_evidences_from_cloud(cloud_config)
                            
                            if success:
                                deleted_total += deleted_count
                                files_total += total_files
                                
                                short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                                results.append(f"✅ {short_name}: {deleted_count} evidencias, {total_files} archivos")
                            else:
                                short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
                                results.append(f"❌ {short_name}: Error al eliminar")
                    
                    admin_evidence_manager.refresh_data(force=True)
                    
                    final_msg = f"""
💥💥💥 **ELIMINACIÓN MASIVA COMPLETADA** 💥💥💥
━━━━━━━━━━━━━━━━━━━

📊 **RESULTADOS FINALES:**
• Nubes procesadas: {len(results)}
• Evidencias eliminadas: {deleted_total}
• Archivos borrados: {files_total}

━━━━━━━━━━━━━━━━━━━
📋 **DETALLE POR NUBE:**
"""
                    
                    for result in results:
                        final_msg += f"\n{result}"
                    
                    final_msg += f"""

━━━━━━━━━━━━━━━━━━━
✅ Todas las nubes han sido limpiadas.
📭 No quedan evidencias en ninguna nube.
━━━━━━━━━━━━━━━━━━━
                    """
                    
                    bot.editMessageText(message, final_msg)
                    
                except Exception as e:
                    bot.editMessageText(message, f'❌ Error: {str(e)}')
                return
            
            elif '/adm_logs' in msgText:
                try:
                    if not memory_stats.has_any_data():
                        bot.editMessageText(message, "⚠️ No hay datos registrados")
                        return
                    
                    uploads = memory_stats.get_recent_uploads(15)
                    deletes = memory_stats.get_recent_deletes(15)
                    
                    logs_msg = "📋 **ÚLTIMOS LOGS**\n"
                    logs_msg += "━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    if uploads:
                        logs_msg += "**⬆️ ÚLTIMAS SUBIDAS:**\n"
                        for log in uploads:
                            logs_msg += f"┣➣ {log['timestamp']} - @{log['username']}: {log['filename']} ({log['file_size_formatted']})\n"
                        logs_msg += "\n"
                    
                    if deletes:
                        logs_msg += "**🗑️ ÚLTIMAS ELIMINACIONES:**\n"
                        for log in deletes:
                            if log['type'] == 'delete_all':
                                logs_msg += f"┣➣ {log['timestamp']} - @{log['username']}: ELIMINÓ TODO ({log.get('deleted_evidences', 1)} evidencia(s), {log.get('deleted_files', '?')} archivos)\n"
                            else:
                                logs_msg += f"┣➣ {log['timestamp']} - @{log['username']}: {log['filename']}\n"
                    
                    bot.editMessageText(message, logs_msg)
                except Exception as e:
                    bot.editMessageText(message, f"❌ Error: {str(e)}")
                return
            
            elif '/adm_users' in msgText:
                try:
                    users = memory_stats.get_all_users()
                    if not users:
                        bot.editMessageText(message, "⚠️ No hay usuarios registrados")
                        return
                    
                    users_msg = "👥 **ESTADÍSTICAS POR USUARIO**\n"
                    users_msg += "━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    for user, data in sorted(users.items(), key=lambda x: x[1]['uploads'], reverse=True):
                        total_size_formatted = format_file_size(data['total_size'])
                        users_msg += f"👤 @{user}\n"
                        users_msg += f"   📤 Subidas: {data['uploads']}\n"
                        users_msg += f"   🗑️ Eliminaciones: {data['deletes']}\n"
                        users_msg += f"   💾 Espacio usado: {total_size_formatted}\n"
                        users_msg += f"   📅 Última actividad: {data['last_activity']}\n\n"
                    
                    bot.editMessageText(message, users_msg)
                except Exception as e:
                    bot.editMessageText(message, f"❌ Error: {str(e)}")
                return
            
            elif '/adm_uploads' in msgText:
                try:
                    uploads = memory_stats.get_recent_uploads(15)
                    if not uploads:
                        bot.editMessageText(message, "⚠️ No hay subidas registradas")
                        return
                    
                    uploads_msg = "📤 **ÚLTIMAS SUBIDAS**\n"
                    uploads_msg += "━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    for i, log in enumerate(uploads, 1):
                        uploads_msg += f"{i}. {log['filename']}\n"
                        uploads_msg += f"   👤 @{log['username']}\n"
                        uploads_msg += f"   📅 {log['timestamp']}\n"
                        uploads_msg += f"   📏 {log['file_size_formatted']}\n"
                        uploads_msg += f"   🔗 {log['moodle_host']}\n\n"
                    
                    bot.editMessageText(message, uploads_msg)
                except Exception as e:
                    bot.editMessageText(message, f"❌ Error: {str(e)}")
                return
            
            elif '/adm_deletes' in msgText:
                try:
                    deletes = memory_stats.get_recent_deletes(15)
                    if not deletes:
                        bot.editMessageText(message, "⚠️ No hay eliminaciones registradas")
                        return
                    
                    deletes_msg = "🗑️ **ÚLTIMAS ELIMINACIONES**\n"
                    deletes_msg += "━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    for i, log in enumerate(deletes, 1):
                        if log['type'] == 'delete_all':
                            deletes_msg += f"{i}. **ELIMINACIÓN MASIVA**\n"
                            deletes_msg += f"   👤 @{log['username']}\n"
                            deletes_msg += f"   📅 {log['timestamp']}\n"
                            deletes_msg += f"   ⚠️ ELIMINÓ {log.get('deleted_evidences', 1)} EVIDENCIA(S)\n"
                            deletes_msg += f"   🗑️ Archivos borrados: {log.get('deleted_files', '?')}\n"
                        else:
                            deletes_msg += f"{i}. {log['filename']}\n"
                            deletes_msg += f"   👤 @{log['username']}\n"
                            deletes_msg += f"   📅 {log['timestamp']}\n"
                            deletes_msg += f"   📁 Evidencia: {log['evidence_name']}\n"
                        
                        deletes_msg += f"   🔗 {log['moodle_host']}\n\n"
                    
                    bot.editMessageText(message, deletes_msg)
                except Exception as e:
                    bot.editMessageText(message, f"❌ Error: {str(e)}")
                return
            
            elif '/adm_cleardata' in msgText:
                try:
                    if not memory_stats.has_any_data():
                        bot.editMessageText(message, "⚠️ No hay datos para limpiar")
                        return
                    
                    result = memory_stats.clear_all_data()
                    bot.editMessageText(message, f"✅ {result}")
                except Exception as e:
                    bot.editMessageText(message, f"❌ Error: {str(e)}")
                return

        # COMANDOS REGULARES DE USUARIO
        if '/mystats' in msgText:
            user_stats = memory_stats.get_user_stats(username)
            if user_stats:
                total_size_formatted = format_file_size(user_stats['total_size'])
                
                stats_msg = f"""
📊 **TUS ESTADÍSTICAS**
━━━━━━━━━━━━━━━━━━━

👤 **Usuario:** @{username}
📤 **Archivos subidos:** {user_stats['uploads']}
🗑️ **Archivos eliminados:** {user_stats['deletes']}
💾 **Espacio total usado:** {total_size_formatted}
📅 **Última actividad:** {user_stats['last_activity']}
🔗 **Nube:** {user_info['moodle_host']}
━━━━━━━━━━━━━━━━━━━
                """
            else:
                stats_msg = f"""
📊 **TUS ESTADÍSTICAS**
━━━━━━━━━━━━━━━━━━━

👤 **Usuario:** @{username}
📤 **Archivos subidos:** 0
🗑️ **Archivos eliminados:** 0
💾 **Espacio total usado:** 0 B
📅 **Última actividad:** Nunca
🔗 **Nube:** {user_info['moodle_host']}
━━━━━━━━━━━━━━━━━━━
ℹ️ Aún no has realizado ninguna acción
                """
            
            bot.editMessageText(message, stats_msg)
            return
        
        elif '/files' == msgText:
            proxy = ProxyCloud.parse(user_info['proxy'])
            client = MoodleClient(user_info['moodle_user'],
                                   user_info['moodle_password'],
                                   user_info['moodle_host'],
                                   user_info['moodle_repo_id'],proxy=proxy)
            loged = client.login()
            if loged:
                all_evidences = client.getEvidences()
                
                visible_list = []
                search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                
                for ev in all_evidences:
                    if ev['name'].endswith(search_pattern):
                        clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                        file_count = len(ev['files']) if 'files' in ev else 0
                        visible_list.append({
                            'name': clean_name,
                            'file_count': file_count,
                            'original': ev
                        })
                
                if len(visible_list) > 0:
                    files_msg = f"📁 **TUS EVIDENCIAS**\n"
                    files_msg += f"━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    for idx, item in enumerate(visible_list):
                        files_msg += f" **{item['name']}** [ {item['file_count']} ]\n"
                        files_msg += f" /txt_{idx} /del_{idx}\n\n"
                   
                    files_msg += f"━━━━━━━━━━━━━━━━━━━\n"
                    files_msg += f"Total: {len(visible_list)} evidencia(s)"
                    
                    bot.editMessageText(message, files_msg)
                else:
                    bot.editMessageText(message, '📭 No hay evidencias disponibles')
                client.logout()
            else:
                bot.editMessageText(message,'➲ Error al conectar con Moodle')
        
        elif '/txt_' in msgText:
            try:
                findex = int(str(msgText).split('_')[1])
                proxy = ProxyCloud.parse(user_info['proxy'])
                client = MoodleClient(user_info['moodle_user'],
                                       user_info['moodle_password'],
                                       user_info['moodle_host'],
                                       user_info['moodle_repo_id'],proxy=proxy)
                loged = client.login()
                if loged:
                    all_evidences = client.getEvidences()
                    
                    visible_list = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                    
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                            visible_list.append({
                                'clean_name': clean_name,
                                'original': ev
                            })
                    
                    if findex < 0 or findex >= len(visible_list):
                        bot.editMessageText(message, '❌ Índice inválido. Use /files para ver la lista.')
                        client.logout()
                        return
                    
                    evindex = visible_list[findex]['original']
                    clean_name = visible_list[findex]['clean_name']
                    
                    txtname = clean_name + '.txt'
                    
                    sendTxt(txtname, evindex['files'], update, bot)
                    
                    client.logout()
                    bot.editMessageText(message,'📄 TXT enviado')
                else:
                    bot.editMessageText(message,'➲ Error al conectar con Moodle')
            except ValueError:
                bot.editMessageText(message, '❌ Formato incorrecto. Use: /txt_0')
            except Exception as e:
                bot.editMessageText(message, f'❌ Error: {str(e)}')
             
        elif '/del_' in msgText:
            try:
                findex = int(str(msgText).split('_')[1])
                proxy = ProxyCloud.parse(user_info['proxy'])
                client = MoodleClient(user_info['moodle_user'],
                                       user_info['moodle_password'],
                                       user_info['moodle_host'],
                                       user_info['moodle_repo_id'],
                                       proxy=proxy)
                loged = client.login()
                if loged:
                    all_evidences = client.getEvidences()
                    
                    visible_list = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                    
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                            visible_list.append({
                                'clean_name': clean_name,
                                'original': ev
                            })
                    
                    if findex < 0 or findex >= len(visible_list):
                        bot.editMessageText(message, '❌ Índice inválido. Use /files para ver la lista.')
                        client.logout()
                        return
                    
                    evfile = visible_list[findex]['original']
                    evidence_clean_name = visible_list[findex]['clean_name']
                    
                    file_count = len(evfile['files']) if 'files' in evfile else 0
                    
                    client.deleteEvidence(evfile)
                    
                    all_evidences = client.getEvidences()
                    
                    updated_visible_list = []
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            clean_name = ev['name'].replace(f"{USER_EVIDENCE_MARKER}{username}", "")
                            updated_visible_list.append({
                                'clean_name': clean_name,
                                'original': ev
                            })
                    
                    client.logout()
                    
                    memory_stats.log_delete(
                        username=username,
                        filename=f"{evidence_clean_name} ({file_count} archivos)",
                        evidence_name=evidence_clean_name,
                        moodle_host=user_info['moodle_host']
                    )
                    
                    confirmation_msg = f"🗑️ **Evidencia eliminada:** {evidence_clean_name}\n"
                    confirmation_msg += f"📁 **Archivos borrados:** {file_count}\n"
                    confirmation_msg += f"━━━━━━━━━━━━━━━━━━━\n"
                    
                    if len(updated_visible_list) > 0:
                        confirmation_msg += f"📋 **Tus evidencias actualizadas:**\n\n"
                        
                        for idx, item in enumerate(updated_visible_list):
                            clean_name = item['clean_name']
                            item_file_count = len(item['original']['files']) if 'files' in item['original'] else 0
                            confirmation_msg += f" **{clean_name}** [ {item_file_count} ]\n"
                            confirmation_msg += f" /txt_{idx} /del_{idx}\n\n"
                        
                        bot.editMessageText(message, confirmation_msg)
                    else:
                        confirmation_msg += f"📭 No hay evidencias disponibles"
                        bot.editMessageText(message, confirmation_msg)
                    
                else:
                    bot.editMessageText(message,'➲ Error al conectar con Moodle')
            except ValueError:
                bot.editMessageText(message, '❌ Formato incorrecto. Use: /del_0')
            except Exception as e:
                bot.editMessageText(message, f'❌ Error: {str(e)}')
                
        elif '/delall' in msgText:
            try:
                proxy = ProxyCloud.parse(user_info['proxy'])
                client = MoodleClient(user_info['moodle_user'],
                                       user_info['moodle_password'],
                                       user_info['moodle_host'],
                                       user_info['moodle_repo_id'],
                                       proxy=proxy)
                loged = client.login()
                if loged:
                    all_evidences = client.getEvidences()
                    
                    user_evidences = []
                    search_pattern = f"{USER_EVIDENCE_MARKER}{username}"
                    for ev in all_evidences:
                        if ev['name'].endswith(search_pattern):
                            user_evidences.append(ev)
                    
                    if not user_evidences:
                        bot.editMessageText(message, '📭 No hay evidencias disponibles')
                        client.logout()
                        return
                    
                    total_evidences = len(user_evidences)
                    total_files = 0
                    
                    for ev in user_evidences:
                        files_in_evidence = ev.get('files', [])
                        total_files += len(files_in_evidence)
                    
                    for item in user_evidences:
                        try:
                            client.deleteEvidence(item)
                        except Exception as e:
                            print(f"Error eliminando evidencia: {e}")
                    
                    client.logout()
                    
                    memory_stats.log_delete_all(
                        username=username, 
                        deleted_evidences=total_evidences, 
                        deleted_files=total_files,
                        moodle_host=user_info['moodle_host']
                    )
                    
                    deletion_msg = f"""
🗑️ **ELIMINACIÓN MASIVA COMPLETADA**
━━━━━━━━━━━━━━━━━━━
📊 **Resumen:**
   • Evidencias eliminadas: {total_evidences}
   • Archivos borrados: {total_files}

━━━━━━━━━━━━━━━━━━━
✅ ¡Todas tus evidencias han sido eliminadas!
📭 No hay evidencias disponibles
                    """
                    
                    bot.editMessageText(message, deletion_msg)
                    
                else:
                    bot.editMessageText(message,'➲ Error al conectar con Moodle')
            except Exception as e:
                bot.editMessageText(message, f'❌ Error: {str(e)}')
                
        elif 'http' in msgText:
            url = msgText
            
            funny_message_sent = None
            
            try:
                headers = {}
                if user_info['proxy']:
                    proxy_dict = ProxyCloud.parse(user_info['proxy'])
                    if 'http' in proxy_dict:
                        headers.update({'Proxy': proxy_dict['http']})
                
                response = requests.head(url, allow_redirects=True, timeout=5, headers=headers)
                file_size = int(response.headers.get('content-length', 0))
                file_size_mb = file_size / (1024 * 1024)
                
                if file_size_mb > 500:
                    funny_message = get_random_large_file_message()
                    warning_msg = bot.sendMessage(update.message.chat.id, 
                                      f"⚠️ {funny_message}\n\n"
                                      f"❌ Tamaño: {file_size_mb:.2f} MB\n\n"
                                      f"⬆️ Subiendo...")
                    funny_message_sent = warning_msg
                
            except Exception as e:
                pass
            
            ddl(update,bot,message,url,file_name='',thread=thread,jdb=jdb)
            
            if funny_message_sent:
                delete_message_after_delay(bot, funny_message_sent.chat.id, funny_message_sent.message_id, 8)
            
        else:
            help_msg = f"""
❓ **COMANDOS DISPONIBLES**
━━━━━━━━━━━━━━━━━━━

📤 **SUBIR ARCHIVOS:**
• Envía un **enlace directo** (http://...)
• Envía un **archivo adjunto**
• Envía **fotos** o **videos**
• Envía **múltiples archivos**

📁 **GESTIONAR:**
• /files - Ver tus evidencias
• /txt_X - Obtener TXT de evidencia
• /del_X - Eliminar evidencia
• /delall - Eliminar todas
• /mystats - Tus estadísticas

👑 **ADMIN** (solo @{ADMIN_USERNAME}):
• /admin - Panel de admin
• /adm_allclouds - Ver todas las nubes

━━━━━━━━━━━━━━━━━━━
            """
            bot.editMessageText(message, help_msg)
            
    except Exception as ex:
        print(f"Error general en onmessage: {str(ex)}")
        print(traceback.format_exc())
        try:
            bot.sendMessage(update.message.chat.id, f'❌ Error: {str(ex)}')
        except:
            pass

# ==============================
# FUNCIÓN PRINCIPAL
# ==============================

def main():
    """Función principal que inicia el bot"""
    bot = ObigramClient(BOT_TOKEN)
    
    # Registrar TODOS los manejadores
    bot.onMessage(onmessage)        # Mensajes de texto y comandos
    bot.onDocument(ondocument)       # Archivos individuales
    bot.onAlbum(onalbum)             # Múltiples archivos (álbumes)
    bot.onPhoto(onphoto)             # Fotos
    bot.onVideo(onvideo)             # Videos
    
    print("✅ Bot iniciado con soporte completo para:")
    print("   • Enlaces HTTP/HTTPS")
    print("   • Archivos adjuntos")
    print("   • Múltiples archivos")
    print("   • Fotos")
    print("   • Videos")
    print("   • Comandos de gestión")
    
    # Registrar limpieza al salir
    import atexit
    atexit.register(temp_manager.cleanup)
    
    bot.run()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Bot detenido por el usuario")
        temp_manager.cleanup()
    except Exception as e:
        print(f"Error fatal: {e}")
        traceback.print_exc()
        main()
