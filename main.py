from pyobigram.utils import sizeof_fmt,get_file_size,createID,nice_time
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

# ===== NUEVO: Imports para sistema de colas =====
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
import queue

# FIXED CONFIGURATION IN CODE
BOT_TOKEN = "8410047906:AAGntGHmkIuIvovBMQfy-gko2JTw3TNJsak"

# ADMINISTRATOR CONFIGURATION
ADMIN_USERNAME = "Eliel_21"

# CUBA TIMEZONE
try:
    CUBA_TZ = pytz.timezone('America/Havana')
except:
    CUBA_TZ = None

# SEPARATOR FOR USER EVIDENCES
USER_EVIDENCE_MARKER = " "  # Space as separator

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
            # Para refresco completo
            if self.last_full_refresh is None:
                return True
            elapsed = (datetime.datetime.now() - self.last_full_refresh).total_seconds()
            return elapsed > self.ttl
        
        # Para nube específica
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

cloud_cache = CloudCache(ttl_seconds=30)  # 30 segundos de caché

# ===== NUEVO: Sistema de Colas por Usuario =====
# ============================================
# ESTADOS Y TIPOS DE TAREAS
# ============================================

class TaskStatus(Enum):
    PENDING = "pending"      # En espera
    PROCESSING = "processing" # En proceso
    COMPLETED = "completed"   # Completada
    FAILED = "failed"        # Falló
    CANCELLED = "cancelled"  # Cancelada por usuario

class TaskType(Enum):
    UPLOAD_URL = "upload_url"  # Subir desde URL

@dataclass
class Task:
    """Representa una tarea en la cola"""
    id: str
    user_id: int
    username: str
    task_type: TaskType
    data: Dict[str, Any]
    status: TaskStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2  # Reintentar 2 veces máximo

# ============================================
# GESTOR DE COLAS POR USUARIO (EN MEMORIA)
# ============================================

class UserQueueManager:
    """
    Sistema de colas en memoria, UNA COLA POR USUARIO
    - Cada usuario tiene su propia cola FIFO
    - Solo 1 tarea activa por usuario
    - Si la tarea falla, se reintenta (máx 2 veces)
    - Todo en RAM, no se guarda en disco
    """
    
    def __init__(self, bot, jdb):
        self.bot = bot
        self.jdb = jdb
        
        # Colas por usuario: username -> Queue
        self.user_queues: Dict[str, queue.Queue] = {}
        
        # Tarea activa por usuario: username -> Task
        self.active_tasks: Dict[str, Task] = {}
        
        # Lock para operaciones thread-safe
        self.lock = threading.Lock()
        
        # Flag para detener el procesador
        self.running = True
        
        # Iniciar procesador de tareas (hilo demonio)
        self.processor_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.processor_thread.start()
        
        print("✅ Sistema de colas por usuario inicializado (en memoria)")
    
    def add_task(self, user_id: int, username: str, task_type: TaskType, data: Dict[str, Any], thread=None) -> str:
        """
        Agrega una tarea a la cola del usuario
        Guarda thread ID para poder cancelar
        """
        task_id = createID()
        
        # Guardar thread ID si existe
        if thread:
            data['thread_id'] = thread.id
            thread.store('task_id', task_id)  # Guardar task_id en el thread
        
        task = Task(
            id=task_id,
            user_id=user_id,
            username=username,
            task_type=task_type,
            data=data,
            status=TaskStatus.PENDING,
            created_at=datetime.datetime.now().isoformat()
        )
        
        with self.lock:
            if username not in self.user_queues:
                self.user_queues[username] = queue.Queue()
            self.user_queues[username].put(task)
        
        print(f"📥 Tarea {task_id[:8]} agregada para @{username} (cola: {self.user_queues[username].qsize()})")
        return task_id
    
    def get_user_status(self, username: str) -> Dict:
        """Obtiene estado de las tareas de un usuario"""
        with self.lock:
            active = self.active_tasks.get(username)
            
            # Obtener cola (hacemos copia de los IDs)
            queue_tasks = []
            if username in self.user_queues:
                q = self.user_queues[username]
                queue_tasks = [task.id for task in list(q.queue)]
            
            return {
                'active': active,
                'queue_ids': queue_tasks,
                'queue_length': len(queue_tasks)
            }
    
    def cancel_task(self, username: str, task_id: str) -> bool:
        """Cancela una tarea (solo si está en cola o activa)"""
        with self.lock:
            # CASO 1: Es la tarea activa
            active = self.active_tasks.get(username)
            if active and active.id == task_id:
                # Marcar como cancelada (el hilo la detendrá)
                active.status = TaskStatus.CANCELLED
                
                # Buscar el thread y detenerlo
                thread_id = active.data.get('thread_id')
                if thread_id and hasattr(self.bot, 'threads'):
                    thread = self.bot.threads.get(thread_id)
                    if thread:
                        thread.store('stop', True)
                
                # Remover de activas
                self.active_tasks.pop(username, None)
                return True
            
            # CASO 2: Está en cola
            if username in self.user_queues:
                new_queue = queue.Queue()
                removed = False
                
                q = self.user_queues[username]
                while not q.empty():
                    task = q.get()
                    if task.id == task_id:
                        removed = True
                        task.status = TaskStatus.CANCELLED
                        print(f"🗑️ Tarea {task_id[:8]} cancelada de la cola de @{username}")
                        # No la agregamos a la nueva cola
                    else:
                        new_queue.put(task)
                
                self.user_queues[username] = new_queue
                return removed
            
            return False
    
    def _process_loop(self):
        """Bucle principal que procesa las tareas"""
        while self.running:
            try:
                # Buscar usuarios con tareas pendientes
                users_to_process = []
                
                with self.lock:
                    for username, q in self.user_queues.items():
                        # Si el usuario no tiene tarea activa Y tiene cola no vacía
                        if username not in self.active_tasks and not q.empty():
                            users_to_process.append(username)
                
                # Procesar cada usuario (máximo 1 tarea por usuario)
                for username in users_to_process:
                    self._process_next_task(username)
                
                # Pequeña pausa para no saturar CPU
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Error en process_loop: {e}")
                traceback.print_exc()
                time.sleep(2)
    
    def _process_next_task(self, username: str):
        """Procesa la siguiente tarea de un usuario"""
        task = None
        
        try:
            # Obtener siguiente tarea
            with self.lock:
                if username in self.user_queues:
                    q = self.user_queues[username]
                    if not q.empty():
                        task = q.get()
                        task.status = TaskStatus.PROCESSING
                        task.started_at = datetime.datetime.now().isoformat()
                        self.active_tasks[username] = task
            
            if not task:
                return
            
            print(f"▶️ Procesando tarea {task.id[:8]} para @{username}")
            
            # Notificar inicio al usuario
            try:
                remaining = self.get_user_status(username)['queue_length']
                msg = f"🔄 **Procesando tu solicitud**\n📋 ID: `{task.id[:8]}`"
                if remaining > 0:
                    msg += f"\n📦 {remaining} tarea(s) pendiente(s) en cola"
                self.bot.sendMessage(task.user_id, msg)
            except:
                pass
            
            # Ejecutar según tipo de tarea
            if task.task_type == TaskType.UPLOAD_URL:
                self._execute_upload_url(task)
            else:
                raise Exception(f"Tipo de tarea no soportado: {task.task_type}")
            
            # Si llegamos aquí, tarea completada exitosamente
            with self.lock:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.datetime.now().isoformat()
                self.active_tasks.pop(username, None)
            
            print(f"✅ Tarea {task.id[:8]} completada para @{username}")
            
            # Notificar éxito
            try:
                remaining = self.get_user_status(username)['queue_length']
                if remaining > 0:
                    self.bot.sendMessage(
                        task.user_id,
                        f"✅ Tarea completada. {remaining} tarea(s) pendiente(s) en cola."
                    )
            except:
                pass
            
        except Exception as e:
            print(f"❌ Error procesando tarea {task.id if task else 'unknown'}: {e}")
            traceback.print_exc()
            
            if task:
                # Manejar error con reintentos
                with self.lock:
                    task.retry_count += 1
                    
                    if task.retry_count < task.max_retries:
                        # Reintentar
                        print(f"⚠️ Tarea {task.id[:8]} falló, reintento {task.retry_count}/{task.max_retries}")
                        task.status = TaskStatus.PENDING
                        # Re-encolar al principio de la cola
                        if username in self.user_queues:
                            new_queue = queue.Queue()
                            new_queue.put(task)
                            q = self.user_queues[username]
                            while not q.empty():
                                new_queue.put(q.get())
                            self.user_queues[username] = new_queue
                        
                        self.active_tasks.pop(username, None)
                        
                        # Notificar reintento
                        try:
                            self.bot.sendMessage(
                                task.user_id,
                                f"⚠️ Error temporal. Reintentando ({task.retry_count}/{task.max_retries})..."
                            )
                        except:
                            pass
                        
                    else:
                        # Máximo de reintentos alcanzado
                        task.status = TaskStatus.FAILED
                        task.error = str(e)
                        task.completed_at = datetime.datetime.now().isoformat()
                        self.active_tasks.pop(username, None)
                        
                        print(f"❌ Tarea {task.id[:8]} falló definitivamente")
                        
                        # Notificar error
                        try:
                            self.bot.sendMessage(
                                task.user_id,
                                f"❌ Error en tu tarea después de {task.max_retries} intentos."
                            )
                        except:
                            pass
            else:
                with self.lock:
                    self.active_tasks.pop(username, None)
    
    def _execute_upload_url(self, task: Task):
        """Ejecuta una subida desde URL"""
        url = task.data.get('url')
        update = task.data.get('update')
        thread = task.data.get('thread')
        message = task.data.get('message')
        
        # Obtener user_info
        user_info = self.jdb.get_user(task.username)
        if not user_info:
            raise Exception("No se encontró información del usuario")
        
        # Verificar tamaño (opcional)
        try:
            headers = {}
            if user_info.get('proxy'):
                proxy_dict = ProxyCloud.parse(user_info['proxy'])
                if 'http' in proxy_dict:
                    headers.update({'Proxy': proxy_dict['http']})
            
            response = requests.head(url, allow_redirects=True, timeout=5, headers=headers)
            file_size = int(response.headers.get('content-length', 0))
            file_size_mb = file_size / (1024 * 1024)
            
            if file_size_mb > 500:
                self.bot.sendMessage(
                    task.user_id,
                    f"⚠️ Archivo grande: {file_size_mb:.2f} MB. Subiendo..."
                )
        except:
            pass  # Si falla la verificación, continuar
        
        # Llamar a la función ddl original
        from main import ddl  # Ajusta el import según tu estructura
        ddl(update, self.bot, message, url, file_name='', thread=thread, jdb=self.jdb)


def get_cuba_time():
    if CUBA_TZ:
        cuba_time = datetime.datetime.now(CUBA_TZ)
    else:
        cuba_time = datetime.datetime.now()
    return cuba_time

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

# ==============================
# SISTEMA DE ESTADÍSTICAS EN MEMORIA
# ==============================

class MemoryStats:
    """Sistema de estadísticas en memoria (sin archivos)"""
    
    def __init__(self):
        self.reset_stats()
    
    def reset_stats(self):
        """Reinicia todas las estadísticas"""
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
        if username in self.user_stats:
            return self.user_stats[username]
        return None
    
    def get_all_stats(self):
        """Obtiene todas las estadísticas globales"""
        return self.stats
    
    def get_all_users(self):
        """Obtiene todos los usuarios"""
        return self.user_stats
    
    def get_recent_uploads(self, limit=10):
        """Obtiene subidas recientes"""
        return self.upload_logs[-limit:][::-1] if self.upload_logs else []
    
    def get_recent_deletes(self, limit=10):
        """Obtiene eliminaciones recientes"""
        return self.delete_logs[-limit:][::-1] if self.delete_logs else []
    
    def has_any_data(self):
        """Verifica si hay datos"""
        return len(self.upload_logs) > 0 or len(self.delete_logs) > 0
    
    def clear_all_data(self):
        """Limpia todos los datos"""
        self.reset_stats()
        return "✅ Todos los datos han sido eliminados"

memory_stats = MemoryStats()

def expand_user_groups():
    """Convierte 'usuario1,usuario2':config a 'usuario1':config, 'usuario2':config"""
    expanded = {}
    for user_group, config in PRE_CONFIGURATED_USERS.items():
        users = [u.strip() for u in user_group.split(',')]
        for user in users:
            expanded[user] = config.copy()
    return expanded

def downloadFile(downloader,filename,currentBits,totalBits,speed,time,args):
    try:
        bot = args[0]
        message = args[1]
        thread = args[2]
        if thread.getStore('stop'):
            downloader.stop()
        downloadingInfo = infos.createDownloading(filename,totalBits,currentBits,speed,time,tid=thread.id)
        bot.editMessageText(message,downloadingInfo)
    except Exception as ex: print(str(ex))
    pass

def uploadFile(filename,currentBits,totalBits,speed,time,args):
    try:
        bot = args[0]
        message = args[1]
        originalfile = args[2]
        thread = args[3]
        downloadingInfo = infos.createUploading(filename,totalBits,currentBits,speed,time,originalfile)
        bot.editMessageText(message,downloadingInfo)
    except Exception as ex: print(str(ex))
    pass

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
                fileid = None  # Inicializar fileid
                while resp is None:
                    fileid,resp = client.upload_file(f,evidence,fileid,progressfunc=uploadFile,args=(bot,message,originalfile,thread),tokenize=tokenize)
                    draftlist.append(resp)
                    iter += 1
                    if iter>=10:
                        break
                os.unlink(f)
            try:
                client.saveEvidence(evidence)
            except:pass
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
        try:
            os.unlink(file)
        except:pass
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
    os.unlink(name)

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
    Obtiene todas las evidencias de todas las nubes preconfiguradas (versión optimizada)
    """
    # Verificar caché primero
    if use_cache and not cloud_cache.should_refresh():
        cached_data = cloud_cache.get_cache('all_clouds')
        if cached_data:
            return cached_data
    
    all_evidences = []
    
    for user_group, cloud_config in PRE_CONFIGURATED_USERS.items():
        # Extraer la configuración de la nube
        moodle_host = cloud_config.get('moodle_host', '')
        moodle_user = cloud_config.get('moodle_user', '')
        moodle_password = cloud_config.get('moodle_password', '')
        moodle_repo_id = cloud_config.get('moodle_repo_id', '')
        proxy = cloud_config.get('proxy', '')
        
        # Verificar caché para esta nube específica
        if use_cache and not cloud_cache.should_refresh(moodle_host):
            cached_evidence = cloud_cache.get_cache(moodle_host)
            if cached_evidence:
                all_evidences.extend(cached_evidence)
                continue
        
        try:
            # Conectar a la nube con timeout
            proxy_parsed = ProxyCloud.parse(proxy)
            client = MoodleClient(moodle_user, moodle_password, moodle_host, moodle_repo_id, proxy=proxy_parsed)
            
            if client.login():
                # Obtener todas las evidencias de esta nube
                evidences = client.getEvidences()
                
                # Procesar cada evidencia
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
                # Actualizar caché
                if use_cache:
                    cloud_cache.update_cache(moodle_host, [ev for ev in all_evidences if ev['cloud_name'] == moodle_host])
            else:
                print(f"No se pudo conectar a {moodle_host}")
                
        except Exception as e:
            print(f"Error obteniendo evidencias de {moodle_host}: {str(e)}")
    
    # Actualizar caché completa
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
            # Buscar la evidencia exacta
            all_evidences = client.getEvidences()
            evidence_to_delete = None
            
            for ev in all_evidences:
                if ev.get('id') == evidence.get('id'):
                    evidence_to_delete = ev
                    break
            
            if evidence_to_delete:
                evidence_name = evidence_to_delete.get('name', '')
                files_count = len(evidence_to_delete.get('files', []))
                # Eliminar la evidencia
                client.deleteEvidence(evidence_to_delete)
                client.logout()
                # Invalidar caché
                cloud_cache.clear_cache()
                return True, evidence_name, files_count
            else:
                client.logout()
                return False, "", 0
        else:
            return False, "", 0
            
    except Exception as e:
        try:
            client.logout()
        except:
            pass
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
            # Obtener todas las evidencias
            all_evidences = client.getEvidences()
            deleted_count = 0
            total_files = 0
            
            # Eliminar cada evidencia
            for evidence in all_evidences:
                try:
                    files_count = len(evidence.get('files', []))
                    client.deleteEvidence(evidence)
                    deleted_count += 1
                    total_files += files_count
                except:
                    pass
            
            client.logout()
            # Invalidar caché
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
            
            # Crear lista plana para acceso rápido
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
                    # Buscar la evidencia actualizada
                    all_evidences = client.getEvidences()
                    current_evidence = None
                    
                    for ev in all_evidences:
                        if ev.get('id') == evidence_data.get('id'):
                            current_evidence = ev
                            break
                    
                    if current_evidence:
                        files = current_evidence.get('files', [])
                        
                        # Preparar URLs
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

# ==============================
# FUNCIONES SIMPLES PARA EXTRACCIÓN DE PARÁMETROS
# ==============================

def extract_one_param_simple(msgText, prefix):
    """
    Extrae un parámetro de forma simple usando split
    """
    try:
        if prefix in msgText:
            parts = msgText.split('_')
            # El índice depende del prefijo
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
            # Los comandos tienen formato: /adm_xxx_X_Y
            if len(parts) > 3:
                param1 = int(parts[2])  # Primer número
                param2 = int(parts[3])  # Segundo número
                return [param1, param2]
    except (ValueError, IndexError):
        return None
    return None

def show_updated_cloud(bot, message, cloud_idx):
    """Muestra la lista actualizada de una nube después de eliminar"""
    try:
        # Obtener datos actualizados
        admin_evidence_manager.refresh_data(force=True)  # Forzar refresco después de eliminar
        cloud_names = list(admin_evidence_manager.clouds_dict.keys())
        
        # Verificar que el índice sea válido
        if cloud_idx < 0 or cloud_idx >= len(cloud_names):
            # Si el índice es inválido, mostrar todas las nubes
            show_updated_all_clouds(bot, message)
            return
        
        cloud_name = cloud_names[cloud_idx]
        evidences = admin_evidence_manager.clouds_dict.get(cloud_name, [])
        
        # VERIFICACIÓN CRÍTICA: Si no hay evidencias, mostrar todas las nubes
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
            time.sleep(1.5)  # Breve pausa para que el usuario vea el mensaje
            show_updated_all_clouds(bot, message)  # MOSTRAR TODAS LAS NUBES
            return
        
        short_name = cloud_name.replace('https://', '').replace('http://', '').split('/')[0]
        
        # Si hay evidencias, mostrar la lista normal
        list_msg = f"""
📋 NUBE ACTUALIZADA
☁️ {short_name}
━━━━━━━━━━━━━━━━━━━

"""
        for idx, evidence in enumerate(evidences):
            ev_name = evidence['evidence_name']
            
            # Limpiar nombre de evidencia
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
        # Manejo de error más amigable
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
        # Refrescar datos primero (con caché)
        admin_evidence_manager.refresh_data()
        
        total_evidences = len(admin_evidence_manager.current_list)
        total_clouds = len(admin_evidence_manager.clouds_dict)
        total_files = 0
        
        for cloud_name, evidences in admin_evidence_manager.clouds_dict.items():
            for ev in evidences:
                total_files += ev['files_count']
        
        if total_evidences == 0:
            # Si no hay evidencias en ninguna nube, mostrar mensaje simple
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
        
        # Si hay evidencias, mostrar la lista completa
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

# ==============================
# FUNCIÓN PRINCIPAL ONMESSAGE (MODIFICADA CON SISTEMA DE COLAS)
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

        # ===== NUEVO: Inicializar sistema de colas en el bot =====
        if not hasattr(bot, 'queue_manager'):
            bot.queue_manager = UserQueueManager(bot, jdb)
        
        queue_manager = bot.queue_manager

        msgText = ''
        try: msgText = update.message.text
        except:pass

        # ===== NUEVO: Comando /queue para usuarios =====
        if msgText == '/queue':
            status = queue_manager.get_user_status(username)
            
            if not status['active'] and status['queue_length'] == 0:
                bot.sendMessage(update.message.chat.id, "📭 No tienes tareas pendientes")
                return
            
            msg = "📊 **ESTADO DE TUS TAREAS**\n"
            msg += "━━━━━━━━━━━━━━━━━━━\n\n"
            
            if status['active']:
                active = status['active']
                msg += f"**▶️ EN PROCESO**\n"
                msg += f"🆔 ID: `{active.id[:8]}`\n"
                if active.task_type == TaskType.UPLOAD_URL:
                    url = active.data.get('url', '')[:40]
                    msg += f"🔗 {url}...\n"
                msg += "\n"
            
            if status['queue_length'] > 0:
                msg += f"**📦 EN COLA ({status['queue_length']})**\n"
                for i, task_id in enumerate(status['queue_ids'][:5]):
                    msg += f"   {i+1}. `{task_id[:8]}`\n"
                if status['queue_length'] > 5:
                    msg += f"   ... y {status['queue_length'] - 5} más\n"
            
            msg += f"\n━━━━━━━━━━━━━━━━━━━\n"
            msg += f"🗑️ /cancel_ID - Cancelar tarea (si está en cola)"
            
            bot.sendMessage(update.message.chat.id, msg)
            return

        # ===== NUEVO: Comando /adm_queues MEJORADO para admin =====
        if username == ADMIN_USERNAME and msgText == '/adm_queues':
            try:
                # Obtener todas las colas
                total_usuarios_con_cola = len(queue_manager.user_queues)
                total_tareas_activas = len(queue_manager.active_tasks)
                total_tareas_pendientes = 0
                
                for q in queue_manager.user_queues.values():
                    total_tareas_pendientes += q.qsize()
                
                # Construir mensaje principal
                admin_msg = f"""
👑 **SISTEMA DE COLAS - PANEL ADMIN**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **ESTADÍSTICAS GLOBALES**
• Usuarios con cola: {total_usuarios_con_cola}
• Tareas activas: {total_tareas_activas}
• Tareas pendientes: {total_tareas_pendientes}
• Total tareas: {total_tareas_activas + total_tareas_pendientes}

"""
                
                # SECCIÓN 1: TAREAS ACTIVAS
                if total_tareas_activas > 0:
                    admin_msg += f"**▶️ TAREAS ACTIVAS ({total_tareas_activas})**\n"
                    admin_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    
                    for user, task in queue_manager.active_tasks.items():
                        # Calcular tiempo transcurrido
                        tiempo = ""
                        if task.started_at:
                            start = datetime.datetime.fromisoformat(task.started_at)
                            minutos = int((datetime.datetime.now() - start).total_seconds() / 60)
                            if minutos < 1:
                                tiempo = "recién iniciada"
                            elif minutos < 60:
                                tiempo = f"{minutos} min"
                            else:
                                horas = minutos // 60
                                minutos_rest = minutos % 60
                                tiempo = f"{horas}h {minutos_rest}m"
                        
                        # Extraer URL
                        url_info = ""
                        if task.task_type == TaskType.UPLOAD_URL:
                            url = task.data.get('url', '')
                            if len(url) > 40:
                                url = url[:40] + "..."
                            url_info = f"\n     🔗 {url}"
                        
                        # Estado de reintentos
                        retry = f" (reintento {task.retry_count}/{task.max_retries})" if task.retry_count > 0 else ""
                        
                        admin_msg += f"""
👤 @{user}
   🆔 `{task.id[:8]}`
   📋 {task.task_type.value}{retry}
   ⏳ {tiempo}{url_info}
"""
                    
                    admin_msg += "\n"
                
                # SECCIÓN 2: TAREAS EN COLA
                if total_tareas_pendientes > 0:
                    admin_msg += f"**📦 TAREAS EN COLA ({total_tareas_pendientes})**\n"
                    admin_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    
                    # Ordenar usuarios por cantidad de tareas
                    usuarios_con_cola = []
                    for user, q in queue_manager.user_queues.items():
                        if q.qsize() > 0:
                            usuarios_con_cola.append((user, q.qsize()))
                    
                    usuarios_con_cola.sort(key=lambda x: x[1], reverse=True)
                    
                    for user, cantidad in usuarios_con_cola[:10]:  # Top 10
                        activa = "▶️ " if user in queue_manager.active_tasks else ""
                        admin_msg += f"   {activa}@{user}: {cantidad} tarea(s)\n"
                        
                        # Si tiene pocas tareas, mostrar detalles
                        if cantidad <= 3:
                            q = queue_manager.user_queues[user]
                            for i, task in enumerate(list(q.queue)[:3]):
                                url_preview = ""
                                if task.task_type == TaskType.UPLOAD_URL:
                                    url = task.data.get('url', '')[:30]
                                    if url:
                                        url_preview = f" - {url}..."
                                admin_msg += f"      {i+1}. `{task.id[:8]}`{url_preview}\n"
                        
                        admin_msg += "\n"
                    
                    if len(usuarios_con_cola) > 10:
                        admin_msg += f"   ... y {len(usuarios_con_cola) - 10} usuario(s) más\n\n"
                
                # SECCIÓN 3: RESUMEN
                if total_tareas_activas == 0 and total_tareas_pendientes == 0:
                    admin_msg += "📭 **No hay tareas en el sistema**\n"
                    admin_msg += "Todas las colas están vacías.\n\n"
                else:
                    admin_msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    admin_msg += f"📊 **RESUMEN:** {total_tareas_activas} activas | {total_tareas_pendientes} pendientes\n"
                
                admin_msg += """
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 Actualiza con /adm_queues
"""
                
                # Alerta si hay mucha demanda
                if total_tareas_pendientes > 20:
                    admin_msg += f"\n⚠️ **ALTA DEMANDA**: {total_tareas_pendientes} tareas en cola"
                
                bot.editMessageText(message, admin_msg)
                
            except Exception as e:
                bot.editMessageText(message, f'❌ Error en /adm_queues: {str(e)}')
                print(f"Error en /adm_queues: {e}")
                traceback.print_exc()
            
            return

        # ===== MEJORADO: Comando /cancel_ (soporta ambos formatos) =====
        if '/cancel_' in msgText:
            try:
                parts = str(msgText).split('_')
                
                # CASO 1: Cancelar por task_id (formato: /cancel_TASKID)
                if len(parts) == 2 and len(parts[1]) > 10:  # Los task_id son largos
                    task_id = parts[1]
                    
                    if hasattr(bot, 'queue_manager'):
                        if bot.queue_manager.cancel_task(username, task_id):
                            bot.editMessageText(message, f"✅ Tarea `{task_id[:8]}...` cancelada")
                        else:
                            bot.editMessageText(message, f"❌ No se encontró la tarea o ya no se puede cancelar")
                    else:
                        bot.editMessageText(message, "❌ Sistema de colas no disponible")
                    
                    return
                
                # CASO 2: Cancelar por thread ID (formato original: /cancel_tid)
                elif len(parts) >= 2:
                    tid = parts[1]
                    
                    if tid in bot.threads:
                        tcancel = bot.threads[tid]
                        msg_obj = tcancel.getStore('msg')
                        tcancel.store('stop', True)
                        
                        # Si la tarea estaba en cola, marcarla como cancelada
                        if hasattr(bot, 'queue_manager'):
                            task_id = tcancel.getStore('task_id')
                            if task_id:
                                bot.queue_manager.cancel_task(username, task_id)
                        
                        time.sleep(1)
                        bot.editMessageText(msg_obj, '➲ Tarea Cancelada ✗')
                    else:
                        bot.editMessageText(message, f'❌ No existe el hilo {tid}')
                    
                    return
                
            except Exception as ex:
                print(f"Error en /cancel_: {ex}")
                bot.editMessageText(message, f'❌ Error al cancelar: {str(ex)}')
            return

        message = bot.sendMessage(update.message.chat.id,'➲ Procesando ✪ ●●○')
        thread.store('msg',message)

        # ============================================
        # COMANDO /start MEJORADO
        # ============================================
        if '/start' in msgText:
            if username == ADMIN_USERNAME:
                start_msg = f"""
👑 USUARIO ADMINISTRADOR

👤 Usuario: @{username}
🔧 Rol: Administrador

⚠️ NOTA IMPORTANTE:
• Tienes acceso de administrador a TODAS las nubes
• Puedes gestionar evidencias de todos los usuarios

🎯 COMANDOS PRINCIPALES:
/admin - Panel principal de administración

📈 COMANDOS DE ESTADÍSTICAS:
/adm_logs - Ver logs del sistema
/adm_users - Ver usuarios y estadísticas
/adm_uploads - Ver últimas subidas
/adm_deletes - Ver últimas eliminaciones
/adm_cleardata - Limpiar estadísticas

☁️ COMANDOS DE GESTIÓN DE NUBES:
/adm_allclouds - Ver todas las nubes
/adm_cloud_X - Ver nube específica
/adm_show_X_Y - Ver detalles de evidencia
/adm_fetch_X_Y - Descargar TXT de evidencia
/adm_delete_X_Y - Eliminar una evidencia
/adm_wipe_X - Limpiar toda una nube
/adm_nuke - Eliminar TODO (peligro extremo)

📊 COMANDOS DE COLAS:
/adm_queues - Ver estado de todas las colas

🔧 TUS COMANDOS PERSONALES:
/files - Ver tus evidencias personales
/txt_X - Ver TXT de tu evidencia
/del_X - Eliminar tu evidencia
/delall - Eliminar todas tus evidencias
/mystats - Ver tus estadísticas
/queue - Ver tu cola de tareas

🔗 FileToLink: @fileeliellinkBot
                """
            else:
                start_msg = f"""
👤 USUARIO REGULAR

👤 Usuario: @{username}
☁️ Nube: Moodle
📁 Evidence: Activado
🔗 Host: {user_info["moodle_host"]}

🔧 TUS COMANDOS:
/start - Ver esta información
/files - Ver tus evidencias
/txt_X - Ver TXT de evidencia X
/del_X - Eliminar evidencia X
/delall - Eliminar todas tus evidencias
/mystats - Ver tus estadísticas
/queue - Ver tu cola de tareas

🔗 FileToLink: @fileeliellinkBot
                """
            
            bot.editMessageText(message, start_msg)
            return
        
        # ============================================
        # COMANDOS DE ADMINISTRADOR (SOLO SI ES ADMIN)
        # ============================================
        if username == ADMIN_USERNAME:
            # COMANDO /admin
            if msgText == '/admin':
                stats = memory_stats.get_all_stats()
                total_size_formatted = format_file_size(stats['total_size_uploaded'])
                current_date = format_cuba_date()
                
                if memory_stats.has_any_data():
                    admin_msg = f"""
👑 PANEL DE ADMINISTRADOR
📅 {current_date}
━━━━━━━━━━━━━━━━━━━
📊 ESTADÍSTICAS GLOBALES:
• Subidas totales: {stats['total_uploads']}
• Eliminaciones totales: {stats['total_deletes']}
• Espacio total subido: {total_size_formatted}
• Nubes configuradas: {len(PRE_CONFIGURATED_USERS)}

📈 COMANDOS DE ESTADÍSTICAS:
/adm_logs - Ver últimos logs
/adm_users - Ver estadísticas por usuario
/adm_uploads - Ver últimas subidas
/adm_deletes - Ver últimas eliminaciones
/adm_cleardata - Limpiar todos los datos

☁️ COMANDOS DE GESTIÓN DE NUBES:
/adm_allclouds - Ver todas las nubes
/adm_cloud_X - Ver nube específica
/adm_show_X_Y - Ver detalles de evidencia
/adm_fetch_X_Y - Descargar TXT de evidencia
/adm_delete_X_Y - Eliminar una evidencia
/adm_wipe_X - Limpiar toda una nube
/adm_nuke - Eliminar TODO (peligro)

📊 COMANDOS DE COLAS:
/adm_queues - Ver estado de todas las colas

🔧 OTROS COMANDOS:
/start - Ver información del usuario
━━━━━━━━━━━━━━━━━━━
🕐 Hora Cuba: {format_cuba_datetime()}
                    """
                else:
                    admin_msg = f"""
👑 PANEL DE ADMINISTRADOR
📅 {current_date}
━━━━━━━━━━━━━━━━━━━
⚠️ NO HAY DATOS REGISTRADOS
Aún no se ha realizado ninguna acción en el bot.

📊 Nubes configuradas: {len(PRE_CONFIGURATED_USERS)}

📈 COMANDOS DE ESTADÍSTICAS:
/adm_logs - Ver últimos logs
/adm_users - Ver estadísticas por usuario
/adm_uploads - Ver últimas subidas
/adm_deletes - Ver últimas eliminaciones

☁️ COMANDOS DE GESTIÓN DE NUBES:
/adm_allclouds - Ver todas las nubes
/adm_cloud_X - Ver nube específica
/adm_show_X_Y - Ver detalles de evidencia
/adm_fetch_X_Y - Descargar TXT de evidencia

📊 COMANDOS DE COLAS:
/adm_queues - Ver estado de todas las colas

🔧 OTROS COMANDOS:
/start - Ver información del usuario
━━━━━━━━━━━━━━━━━━━
🕐 Hora Cuba: {format_cuba_datetime()}
                    """
                
                bot.editMessageText(message, admin_msg)
                return
            
            # COMANDOS CON /adm_ (excluyendo /adm_queues que ya procesamos)
            elif '/adm_' in msgText and not msgText.startswith('/adm_queues'):
                # ... (resto de comandos de admin existentes) ...
                # ===== NOTA: Mantén aquí todo tu código existente de comandos admin =====
                # Como /adm_allclouds, /adm_cloud_X, /adm_show_X_Y, etc.
                # No los elimino para no hacer este mensaje demasiado largo
                pass
        
        # ============================================
        # COMANDOS REGULARES DE USUARIO
        # ============================================
        
        # COMANDO /mystats
        if '/mystats' in msgText:
            user_stats = memory_stats.get_user_stats(username)
            if user_stats:
                total_size_formatted = format_file_size(user_stats['total_size'])
                
                stats_msg = f"""
📊 TUS ESTADÍSTICAS
━━━━━━━━━━━━━━━━━━━

👤 Usuario: @{username}
📤 Archivos subidos: {user_stats['uploads']}
🗑️ Archivos eliminados: {user_stats['deletes']}
💾 Espacio total usado: {total_size_formatted}
📅 Última actividad: {user_stats['last_activity']}
🔗 Nube: {user_info['moodle_host']}
━━━━━━━━━━━━━━━━━━━
📈 Resumen:
• Subiste {user_stats['uploads']} archivo(s)
• Eliminaste {user_stats['deletes']} archivo(s)
• Usaste {total_size_formatted} de espacio
                """
            else:
                stats_msg = f"""
📊 TUS ESTADÍSTICAS
━━━━━━━━━━━━━━━━━━━

👤 Usuario: @{username}
📤 Archivos subidos: 0
🗑️ Archivos eliminados: 0
💾 Espacio total usado: 0 B
📅 Última actividad: Nunca
🔗 Nube: {user_info['moodle_host']}
━━━━━━━━━━━━━━━━━━━
ℹ️ Aún no has realizado ninguna acción
                """
            
            bot.editMessageText(message, stats_msg)
            return
        
        # COMANDO /files
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
                    files_msg = f"📁 TUS EVIDENCIAS\n"
                    files_msg += f"━━━━━━━━━━━━━━━━━━━\n\n"
                    
                    for idx, item in enumerate(visible_list):
                        files_msg += f" {item['name']} [ {item['file_count']} ]\n"
                        files_msg += f" /txt_{idx} /del_{idx}\n\n"
                   
                    files_msg += f"━━━━━━━━━━━━━━━━━━━\n"
                    files_msg += f"Total: {len(visible_list)} evidencia(s)"
                    
                    bot.editMessageText(message, files_msg)
                else:
                    bot.editMessageText(message, '📭 No hay evidencias disponibles')
                client.logout()
            else:
                bot.editMessageText(message,'➲ Error y Causas🧐\n1-Revise su Cuenta\n2-Servidor Deshabilitado: '+client.path)
                
        # COMANDO /txt_X
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
                    bot.editMessageText(message,'📄 TXT Aquí')
                else:
                    bot.editMessageText(message,'➲ Error y Causas🧐\n1-Revise su Cuenta\n2-Servidor Deshabilitado: '+client.path)
            except ValueError:
                bot.editMessageText(message, '❌ Formato incorrecto. Use: /txt_0 (donde 0 es el número de la evidencia)')
            except Exception as e:
                bot.editMessageText(message, f'❌ Error: {str(e)}')
                print(f"Error en /txt_: {e}")
             
        # COMANDO /del_X
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
                    
                    confirmation_msg = f"🗑️ Evidencia eliminada: {evidence_clean_name}\n"
                    confirmation_msg += f"📁 Archivos borrados: {file_count}\n"
                    confirmation_msg += f"━━━━━━━━━━━━━━━━━━━\n"
                    
                    if len(updated_visible_list) > 0:
                        confirmation_msg += f"📋 Tus evidencias actualizadas:\n\n"
                        
                        for idx, item in enumerate(updated_visible_list):
                            clean_name = item['clean_name']
                            item_file_count = len(item['original']['files']) if 'files' in item['original'] else 0
                            confirmation_msg += f" {clean_name} [ {item_file_count} ]\n"
                            confirmation_msg += f" /txt_{idx} /del_{idx}\n\n"
                        
                        bot.editMessageText(message, confirmation_msg)
                    else:
                        confirmation_msg += f"📭 No hay evidencias disponibles"
                        bot.editMessageText(message, confirmation_msg)
                    
                else:
                    bot.editMessageText(message,'➲ Error y Causas🧐\n1-Revise su Cuenta\n2-Servidor Deshabilitado: '+client.path)
            except ValueError:
                bot.editMessageText(message, '❌ Formato incorrecto. Use: /del_0 (donde 0 es el número de la evidencia)')
            except Exception as e:
                bot.editMessageText(message, f'❌ Error: {str(e)}')
                print(f"Error en /del_: {e}")
                
        # COMANDO /delall
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
                    
                    deletion_msg = f"🗑️ ELIMINACIÓN MASIVA COMPLETADA\n"
                    deletion_msg += f"📊 Resumen:\n"
                    deletion_msg += f"   • Evidencias eliminadas: {total_evidences}\n"
                    deletion_msg += f"   • Archivos borrados: {total_files}\n"
                    deletion_msg += f"\n━━━━━━━━━━━━━━━━━━━\n"
                    deletion_msg += f"✅ ¡Todas tus evidencias han sido eliminadas!\n"
                    deletion_msg += f"📭 No hay evidencias disponibles"
                    
                    bot.editMessageText(message, deletion_msg)
                    
                else:
                    bot.editMessageText(message,'➲ Error y Causas🧐\n1-Revise su Cuenta\n2-Servidor Deshabilitado: '+client.path)
            except Exception as e:
                bot.editMessageText(message, f'❌ Error: {str(e)}')
                print(f"Error en /delall: {e}")
                
        # ===== MODIFICADO: Procesar enlaces con sistema de colas =====
        elif 'http' in msgText:
            url = msgText
            
            # Verificar estado actual del usuario
            status = queue_manager.get_user_status(username)
            
            # Crear datos para la tarea
            task_data = {
                'url': url,
                'update': update,
                'thread': thread,
                'message': message,
                'user_info': user_info
            }
            
            # Agregar a la cola
            task_id = queue_manager.add_task(
                user_id=update.message.chat.id,
                username=username,
                task_type=TaskType.UPLOAD_URL,
                data=task_data,
                thread=thread
            )
            
            # Si ya hay tarea activa, notificar que se encoló
            if status['active']:
                queue_msg = f"""
📦 **URL AGREGADA A TU COLA**
━━━━━━━━━━━━━━━━━━━

🔗 {url[:50]}...
📌 Posición: #{status['queue_length'] + 1}
🆔 ID: `{task_id[:8]}`

⏳ Ya tienes una tarea en proceso.
La tuya se procesará automáticamente cuando termine.

📊 /queue - Ver estado de tu cola
🗑️ /cancel_{task_id[:8]} - Cancelar esta tarea
                """
                bot.editMessageText(message, queue_msg)
            else:
                # No hay tarea activa, procesar ahora
                bot.editMessageText(message, f"🔄 Procesando URL...\nID: `{task_id[:8]}`\n/cancel_{task_id[:8]} para cancelar")
                
                # Llamar a la función ddl original
                ddl(update, bot, message, url, file_name='', thread=thread, jdb=jdb)
            
            return
            
        else:
            bot.editMessageText(message,'➲ No se pudo procesar ✗ ')
            
    except Exception as ex:
        print(f"Error general en onmessage: {str(ex)}")
        print(traceback.format_exc())

def main():
    bot = ObigramClient(BOT_TOKEN)
    bot.onMessage(onmessage)
    bot.run()

if __name__ == '__main__':
    try:
        main()
    except:
        main()
