#!/usr/bin/python
# coding: utf-8
# +-------------------------------------------------------------------
# | 阿里云对象存储OS平台客户端
# +-------------------------------------------------------------------
# | Copyright (c) 2015-2099 宝塔软件(http://bt.cn) All rights reserved.
# +-------------------------------------------------------------------
# | Author: linxiao <940950943@qq.com>
# +-------------------------------------------------------------------
from __future__ import absolute_import, print_function, division

import os
import platform
import random
import re
import string
import sys
import time
import json

BASE_PATH = "/www/server/panel"

os.chdir(BASE_PATH)
sys.path.insert(0, "class/")

import oss2
from oss2.exceptions import NoSuchKey, OssError, NotFound
import public, db


PROGRESS_FILE_NAME = "PROGRESS_FILE_NAME"

_ver = sys.version_info
#: Python 2.x?
is_py2 = (_ver[0] == 2)

#: Python 3.x?
is_py3 = (_ver[0] == 3)

if is_py2:
    reload(sys)
    sys.setdefaultencoding('utf-8')


def report_progress(consumed_bytes, total_bytes):
    """上传进度回调函数

    本函数依赖系统环境变量 PROGRESS_FILE_NAME 所指定的文件，进度信息会写入到该文件当中
    进度格式:
    上传百分比|速度(Mb/s)|时间(s)|上传字节|总字节|开始时间戳
    :param consumed_bytes: 已上传字节数
    :param total_bytes: 总字节数
    """
    import public
    p_file = os.environ[PROGRESS_FILE_NAME]
    rate = int(100 * (float(consumed_bytes) / float(total_bytes)))
    if consumed_bytes == 0:
        start_time = time.time()
    else:
        p_text = public.readFile(p_file)
        if not p_text:
            return
        start_time = float(p_text.split("|")[-1])
    now = time.time()
    diff = round(now - start_time, 2)
    speed = round(consumed_bytes / diff / 1024 / 1024, 2) if diff > 0 else 0
    progress_text = "{0}%|{1}Mb/s|{2}|{3}|{4}|{5}".format(
        rate, speed, diff, consumed_bytes, total_bytes, start_time
    )
    if consumed_bytes == total_bytes:
        progress_text += "\n"
    public.writeFile(p_file, progress_text)
    sys.stdout.write("\r" + progress_text)
    sys.stdout.flush()


def percentage(consumed_bytes, total_bytes):
    """命令行进度回调

    :param consumed_bytes:
    :param total_bytes:
    :return:
    """
    if total_bytes:
        rate = int(100 * (float(consumed_bytes) / float(total_bytes)))
        display_consumed = round(consumed_bytes / 1024 / 1024, 2)
        display_total = round(total_bytes / 1024 / 1024, 2)
        progress_text = '{0}%|{1}M|{2}M'.format(
            rate, display_consumed, display_total)
        sys.stdout.write("\r" + progress_text)
        sys.stdout.flush()


def get_tmpdir_path():
    """获取本地临时目录

    兼容: linux,windows
    """
    sysstr = platform.system().lower()
    tmp_dir = ""
    if sysstr == "linux":
        tmp_dir = "/tmp/"
    elif sysstr == "windows":
        base_path = os.getenv("BT_PANEL")
        tmp_dir = os.path.join(base_path, "tmp")

    if not os.path.exists(tmp_dir):
        os.mkdir(tmp_dir)

    return tmp_dir


def get_text_timestamp():
    import time
    timestamp = time.time()
    text = "" + repr(timestamp)
    text = text.replace(".", "")
    return text


def generate_random_str():
    text = get_text_timestamp()
    rand_text = "".join(random.sample(string.ascii_letters, 5))
    rand_text = text + rand_text
    return rand_text


def convert_time(tmsp):
    import datetime
    if tmsp:
        mtime = datetime.datetime.fromtimestamp(tmsp)
        mtime += datetime.timedelta(hours=8)
        ts = int(
            (time.mktime(mtime.timetuple()) + mtime.microsecond / 1000000.0))
        return ts
    return tmsp


def verify_dir_name(dir_name):
    """验证目录名是否包含非法字符

    """
    invalid_symbol = [
        "%2F",  # 防止被替换成/
    ]
    for s in invalid_symbol:
        if dir_name.find(s) != -1:
            return False
    return True


"""
=============自定义异常===================
"""


class OsError(Exception):
    """OS端异常"""


class ObjectNotFound(OsError):
    """对象不存在时抛出的异常"""

    def __init__(self, *args, **kwargs):
        message = "文件对象不存在。"
        super(ObjectNotFound, self).__init__(message, *args, **kwargs)


class APIError(Exception):
    """API参数错误异常"""

    def __init__(self, *args, **kwargs):
        _api_error_msg = 'API资料校验失败，请核实!'
        super(APIError, self).__init__(_api_error_msg, *args, **kwargs)


"""
=============OSClient===================
"""


class OSClient(object):
    _name = ""
    _title = ""
    error_msg = ""
    default_backup_path = "/bt_backup/"
    backup_path = default_backup_path
    CONFIG_SEPARATOR = "|"
    config_file = "config.conf"
    delimiter = "/"
    auth = None
    _inode_min = 10
    _exclude = ""
    _db_mysql = None
    _err_log = '/tmp/backup_err.log'

    def __init__(self, load_config=True, config_file=None):
        if config_file:
            self.config_file = config_file
        self.__auth = None

        # 控制客户端是否从配置文件加载配置
        if load_config:
            data = self.get_config()
            self.init_config(data)

    #########################
    #####OS客户端自定义实现#####
    #########################

    def init_config(self, data):
        """初始化配置参数

        data: 配置文件信息
        """

        return False

    def get_config(self):
        """从配置文件读取配置信息"""

    def re_auth(self):
        """OS客户端重写

        已弃用
        """
        return True

    def build_auth(self):
        """OS客户端重写

        已弃用
        """
        return self.auth

    def get_list(self, path="/"):
        """子类实现获取文件列表

        参考以下字段返回文件列表
        """
        mlist = {
            "list": [
                # 1. 文件夹
                {
                    "name": "",  # 文件名称
                    "type": None,  # type为None表示是文件夹
                },
                # 2. 文件
                {
                    "name": "",  # 文件名称
                    "download": "",
                    "size": "",  # 文件大小
                    "time": "",  # 上传时间
                }
            ],
            "path": "/",
        }
        return mlist

    def generate_download_url(self, object_name):
        """os客户端实现生成下载链接"""
        return ""

    def resumable_upload(self, *arg, **kwargs):
        """断点续传子类实现"""
        raise RuntimeError("不支持上传操作！")

    def delete_object_by_os(self, object_name):
        """OS客户端实现删除操作"""
        raise RuntimeError("文件无法被删除！")

    def get_lib(self):
        """注册计划任务"""
        return True

    #########################
    ######OS客户端通用实现######
    #########################

    def get_base_path(self):
        """根据操作系统获取运行基础路径"""
        return "/www/server/panel"

    def get_setup_path(self):
        """插件安装路径"""
        return os.path.join("plugin", self._name)

    def get_config_file(self):
        """获取配置文件路径"""

        path = os.path.join(self.get_setup_path(), self.config_file);
        return path

    def get_bak_config_file(self):
        return os.path.join(self.get_base_path(), "data",
                            self._name + "AS.conf")

    def get_old_bak_config_file(self):
        return os.path.join(self.get_base_path(), "data",
                            self._name + "As.conf")

    def set_config(self, conf):
        """写入配置文件"""

        path = self.get_config_file()
        public.writeFile(path, json.dumps(conf));

        bak_path = self.get_bak_config_file()
        public.writeFile(bak_path, json.dumps(conf))
        return True

    # 取目录路径
    def get_path(self, path):
        if path == '/': path = '';
        if path[:1] == '/':
            path = path[1:];
        if path[-1:] != '/': path += '/';
        if path == '/': path = '';
        return path.replace('//', '/');

    def build_object_name(self, data_type, file_name):
        """根据数据类型构建对象存储名称

        :param data_type:
        :param file_name:
        :return:
        """

        import re

        prefix_dict = {
            "site": "web",
            "database": "db",
            "path": "path",
        }
        file_regx = prefix_dict.get(data_type) + "_(.+)_20\d+_\d+\."
        sub_search = re.search(file_regx, file_name)
        sub_path_name = ""
        if sub_search:
            sub_path_name = sub_search.groups()[0]
            sub_path_name += '/'

        # 构建OS存储路径
        object_name = self.backup_path + \
                      data_type + '/' + \
                      sub_path_name + \
                      file_name

        if object_name[:1] == "/":
            object_name = object_name[1:]

        return object_name

    def upload_file(self, file_name, data_type=None, *args, **kwargs):
        """按照数据类型上传文件

        针对 panelBackup v1.2以上调用
        :param file_name: 上传文件名称
        :param data_type: 数据类型 site/database/path
        :return: True/False
        """
        try:
            import re
            # 根据数据类型提取子分类名称
            # 比如data_type=database，子分类名称是数据库的名称。
            # 提取方式是从file_name中利用正则规则去提取。
            self.error_msg = ""

            if not file_name or not data_type:
                _error_msg = "文件参数错误。"
                print(_error_msg)
                self.error_msg = _error_msg
                return False

            file_name = os.path.abspath(file_name)
            temp_name = os.path.split(file_name)[1]
            object_name = self.build_object_name(data_type, temp_name)

            return self.resumable_upload(file_name,
                                         object_name=object_name,
                                         *args,
                                         **kwargs)
        except Exception as e:
            if self.error_msg:
                self.error_msg += r"\n"
            self.error_msg += "文件上传出现错误：{}".format(str(e))
            return False

    def delete_object(self, object_name, retries=2):
        """删除对象

        :param object_name:
        :param retries: 重试次数，默认2次
        :return: True 删除成功
                其他 删除失败
        """

        try:
            return self.delete_object_by_os(object_name)
        except Exception as e:
            print("删除文件异常：")
            print(e)

        # 重试
        if retries > 0:
            print("重新尝试删除文件{}...".format(object_name))
            return self.delete_object(
                object_name,
                retries=retries - 1)
        return False

    def delete_file(self, file_name, data_type=None):
        """删除文件

        针对 panelBackup v1.2以上调用
        根据传入的文件名称和文件数据类型构建对象名称，再删除
        :param file_name:
        :param data_type: 数据类型 site/database/path
        :return: True 删除成功
                其他 删除失败
        """

        object_name = self.build_object_name(data_type, file_name)
        return self.delete_object(object_name)

    # 备份网站
    def backupSite(self, name, count, exclude=[]):
        self.echo_start()
        data_type = "site"
        sql = db.Sql();
        path = sql.table('sites').where('name=?', (name,)).getField('path');
        self.echo_info('备份网站：{}'.format(name))
        self.echo_info('网站根目录：{}'.format(path))

        startTime = time.time();
        if not path:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "网站[" + name + "]不存在!"
            self.echo_error("★[" + endDate + "] " + log)
            self.echo_end()
            return;

        p_size = public.get_path_size(path)
        self.echo_info("目录大小：{}".format(public.to_size(p_size)))

        backup_path = sql.table('config').where("id=?", (1,)).getField(
            'backup_path') + '/site';
        if not os.path.exists(backup_path): public.ExecShell(
            "mkdir -p " + backup_path);

        base_file_name = "web_" + name + "_" + time.strftime(
            '%Y%m%d_%H%M%S', time.localtime()) + '.tar.gz'
        filename = backup_path + "/" + base_file_name

        self.get_exclude(exclude)
        exclude_config = self._exclude
        if not self._exclude:
            exclude_config = "未设置"

        disk_path, disk_free, disk_inode = self.get_disk_free(filename)
        self.echo_info("分区{}可用磁盘空间为：{}，可用Inode为：{}".format(
            disk_path,
            public.to_size(disk_free),
            disk_inode))
        if disk_path:
            if disk_free < p_size:
                self.echo_error(
                    "目标分区可用的磁盘空间小于{},无法完成备份，请增加磁盘容量，或在设置页面更改默认备份目录!".format(
                        public.to_size(p_size)))
                return False

            if disk_inode < self._inode_min:
                self.echo_error(
                    "目标分区可用的Inode小于{},无法完成备份，请增加磁盘容量，或在设置页面更改默认备份目录!".format(
                        self._inode_min))
                return False

        public.ExecShell("cd " +
                         os.path.dirname(path) +
                         " && tar zcvf '" + filename +
                         "' " + self._exclude + " '" +
                         os.path.basename(path) +
                         "' 2>{err_log} 1> /dev/null".format(
                             err_log=self._err_log))
        endDate = time.strftime('%Y/%m/%d %X', time.localtime())

        if not os.path.exists(filename):
            log = "网站[" + name + "]备份失败!"
            self.echo_error("★[" + endDate + "] " + log)
            self.echo_end()
            return;

        self.echo_info("站点已备份到:" + filename)

        # 上传文件
        self.echo_info("正在上传到{}，请稍候...".format(self._title))
        if self.upload_file(filename, data_type=data_type):
            self.echo_info("已成功上传到{}".format(self._title))
        else:
            self.echo_error('错误：文件上传失败，跳过本次备份!')
            if os.path.exists(filename):
                os.remove(filename)
            return False

        object_name = self.build_object_name(data_type, base_file_name)
        outTime = time.time() - startTime
        db_filename = object_name + self.CONFIG_SEPARATOR + self._name
        pid = sql.table('sites').where('name=?', (name,)).getField('id');
        sql.table('backup').add('type,name,pid,filename,addtime,size', (
            '0', base_file_name, pid, db_filename, endDate,
            os.path.getsize(filename)))
        log = "网站[" + name + "]已成功备份到" + self._title + ",用时[" + str(
            round(outTime, 2)) + "]秒";
        public.WriteLog('计划任务', log)
        self.echo_info(u"★[" + endDate + "] " + log)
        self.echo_info(u"保留最新的[" + count + "]份备份")
        self.echo_info(u"排除规则: " + exclude_config)

        # 清理本地文件
        if os.path.exists(filename):
            os.remove(filename)

        # 清理多余备份
        backups = sql.table('backup').where(
            'type=? and pid=? and '
            'filename LIKE \'%{}%\''.format(self._name),
            ('0', pid)).field('id,name,filename').select();

        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                _base_file_name = backup["name"]
                _local_file_name = os.path.join(backup_path,
                                                _base_file_name)

                if os.path.isfile(_local_file_name):
                    public.ExecShell("rm -f " + _local_file_name);
                    self.echo_info("已清理本地备份文件:" + _local_file_name)

                _file_name = backup["filename"]
                if _file_name.find(self.CONFIG_SEPARATOR) != -1:
                    os_file_name = _file_name.split(self.CONFIG_SEPARATOR)[0]
                else:
                    os_file_name = _file_name
                self.delete_object(os_file_name)
                sql.table('backup').where('id=?', (backup['id'],)).delete();
                num -= 1;
                self.echo_info("已清理{}过期备份文件：".format(self._title) +
                               os_file_name)
                if num < 1: break;

        if os.path.exists(self._err_log):
            os.remove(self._err_log)
        self.echo_end()
        return None

    # 配置
    def mypass(self, act, root):
        conf_file = '/etc/my.cnf'
        public.ExecShell("sed -i '/user=root/d' {}".format(conf_file))
        public.ExecShell("sed -i '/password=/d' {}".format(conf_file))
        if act:
            mycnf = public.readFile(conf_file);
            src_dump = "[mysqldump]\n"
            sub_dump = src_dump + "user=root\npassword=\"{}\"\n".format(root);
            if not mycnf: return False
            mycnf = mycnf.replace(src_dump, sub_dump)
            if len(mycnf) > 100: public.writeFile(conf_file, mycnf);
            return True
        return True

    # 备份数据库
    def backupDatabase(self, name, count):
        self.echo_start()
        os_title = self._title
        data_type = "database"

        self.echo_info('备份数据库：{}'.format(name))
        sql = db.Sql();
        path = sql.table('databases').where('name=?', (name,)).getField('id');

        startTime = time.time();
        if not path:
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + name + "]不存在!"
            self.echo_error("★[" + endDate + "] " + log)
            self.echo_end()
            return;

        import panelMysql
        if not self._db_mysql: self._db_mysql = panelMysql.panelMysql()
        d_tmp = self._db_mysql.query(
            "select sum(DATA_LENGTH)+sum(INDEX_LENGTH) from "
            "information_schema.tables where table_schema='%s'" % name)
        p_size = self.map_to_list(d_tmp)[0][0]

        if p_size is None:
            self.echo_error('指定数据库 `{}` 没有任何数据!'.format(name))
            self.echo_end()
            return

        self.echo_info("数据库大小：{}".format(public.to_size(p_size)))

        character = public.get_database_character(name)
        self.echo_info("数据库字符集：{}".format(character))

        backup_path = sql.table('config').where("id=?", (1,)).getField(
            'backup_path') + '/database';
        if not os.path.exists(backup_path): public.ExecShell(
            "mkdir -p " + backup_path);

        base_file_name = "db_" + name + "_" + time.strftime(
            '%Y%m%d_%H%M%S', time.localtime()) + ".sql.gz"
        filename = os.path.join(backup_path, base_file_name)

        disk_path, disk_free, disk_inode = self.get_disk_free(filename)
        self.echo_info("分区{}可用磁盘空间为：{}，可用Inode为：{}".format(
            disk_path,
            public.to_size(disk_free),
            disk_inode))
        if disk_path:
            if disk_free < p_size:
                self.echo_error(
                    "目标分区可用的磁盘空间小于{},无法完成备份，请增加磁盘容量，或在设置页面更改默认备份目录!".format(
                        public.to_size(p_size)))
                return False

            if disk_inode < self._inode_min:
                self.echo_error(
                    "目标分区可用的Inode小于{},无法完成备份，请增加磁盘容量，或在设置页面更改默认备份目录!".format(
                        self._inode_min))
                return False

        stime = time.time()
        self.echo_info("开始导出数据库：{}".format(public.format_date(times=stime)))

        if os.path.exists(filename):
            os.remove(filename)

        mysql_root = sql.table('config').where("id=?", (1,)).getField(
            'mysql_root')
        self.mypass(True, mysql_root)

        public.ExecShell(
            "/www/server/mysql/bin/mysqldump --default-character-set=" +
            character + " --force --opt " + name + " | gzip > " + filename)

        self.mypass(False, mysql_root)

        if not os.path.exists(filename):
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = "数据库[" + name + "]备份失败!"
            self.echo_error("★[" + endDate + "] " + log)
            self.echo_end()
            return;

        gz_size = os.path.getsize(filename)
        if gz_size < 400:
            self.echo_error("数据库导出失败!")
            self.echo_info(public.readFile(self._err_log))
            return False

        self.echo_info("数据库已备份到本地:" + filename)

        # 上传文件
        self.echo_info("正在上传到{}，请稍候...".format(self._title))
        if self.upload_file(filename, data_type=data_type):
            self.echo_info("已成功上传到{}".format(self._title))
        else:
            self.echo_error('错误：文件上传失败，跳过本次备份!')
            if os.path.exists(filename):
                os.remove(filename)
            return False

        object_name = self.build_object_name(data_type, base_file_name)
        endDate = time.strftime('%Y/%m/%d %X', time.localtime())
        outTime = time.time() - startTime
        pid = sql.table('databases').where('name=?', (name,)).getField('id');

        tag = self.CONFIG_SEPARATOR + self._name
        db_filename = object_name + tag
        sql.table('backup').add('type,name,pid,filename,addtime,size', (
            1, base_file_name, pid, db_filename, endDate,
            os.path.getsize(filename)))
        log = "数据库[" + name + "]已成功备份到" + os_title + ",用时[" + str(
            round(outTime, 2)) + "]秒";
        public.WriteLog('计划任务', log)
        self.echo_info("★[" + endDate + "] " + log)
        self.echo_info("保留最新的[" + count + "]份备份")

        # 清理本地文件
        if os.path.exists(filename):
            os.remove(filename)

        # 清理多余备份
        backups = sql.table('backup').where(
            'type=? and pid=? and filename '
            'LIKE \'%{}%\''.format(self._name),
            ('1', pid)).field('id,name,filename').select();

        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                _base_file_name = backup["name"]
                _local_file_name = os.path.join(backup_path, _base_file_name)
                if os.path.isfile(_local_file_name):
                    public.ExecShell("rm -f " + _local_file_name);
                    self.echo_info("已清理本地备份文件:" + _local_file_name)

                _file_name = backup["filename"]
                if _file_name.find(self.CONFIG_SEPARATOR) != -1:
                    _object_name = _file_name.split(self.CONFIG_SEPARATOR)[0]
                else:
                    _object_name = self.build_object_name(data_type,
                                                          _base_file_name)
                self.delete_object(_object_name)

                sql.table('backup').where('id=?', (backup['id'],)).delete();
                num -= 1;
                self.echo_info(
                    "已清理{}过期备份文件：".format(self._title) + _object_name)
                if num < 1: break;

        if os.path.exists(self._err_log):
            os.remove(self._err_log)
        self.echo_end()

    # 备份指定目录
    def backupPath(self, path, count, exclude=[]):
        self.echo_start()
        data_type = "path"

        sql = db.Sql();
        startTime = time.time();
        if path[-1:] == '/': path = path[:-1]

        self.echo_info('备份目录：{}'.format(path))
        p_size = public.get_path_size(path)
        self.echo_info("目录大小：{}".format(public.to_size(p_size)))

        self.get_exclude(exclude)
        exclude_config = self._exclude
        if not self._exclude:
            exclude_config = "未设置"

        # TODO(LX) 同名目录备份影响验证
        name = os.path.basename(path)

        backup_path = os.path.join(
            sql.table('config').where("id=?", (1,)).getField('backup_path'),
            data_type);
        if not os.path.exists(backup_path): os.makedirs(backup_path, 384);
        base_file_name = "path_" + name + "_" + time.strftime(
            '%Y%m%d_%H%M%S', time.localtime()) + '.tar.gz'
        filename = os.path.join(backup_path, base_file_name)

        disk_path, disk_free, disk_inode = self.get_disk_free(filename)
        self.echo_info("分区{}可用磁盘空间为：{}，可用Inode为：{}".format(disk_path,
                                                           public.to_size(
                                                               disk_free),
                                                           disk_inode))
        if disk_path:
            if disk_free < p_size:
                self.echo_error(
                    "目标分区可用的磁盘空间小于{},无法完成备份，请增加磁盘容量，或在设置页面更改默认备份目录!".format(
                        public.to_size(p_size)))
                return False

            if disk_inode < self._inode_min:
                self.echo_error(
                    "目标分区可用的Inode小于{},无法完成备份，请增加磁盘容量，或在设置页面更改默认备份目录!".format(
                        self._inode_min))
                return False

        stime = time.time()
        self.echo_info("开始压缩文件：{}".format(public.format_date(times=stime)))

        if os.path.exists(filename):
            os.remove(filename)

        os.system("cd " + os.path.dirname(path) +
                  " && tar zcvf '" + filename + "' " +
                  self._exclude + " '" + os.path.basename(path) +
                  "' 2>{err_log} 1> /dev/null".format(
                      err_log=self._err_log))

        if not os.path.exists(filename):
            endDate = time.strftime('%Y/%m/%d %X', time.localtime())
            log = u"目录[" + path + "]备份失败"
            self.echo_info(u"★[" + endDate + "] " + log)
            self.echo_end()
            return;

        tar_size = os.path.getsize(filename)
        if tar_size < 1:
            self.echo_error("数据压缩失败")
            self.echo_info(public.readFile(self._err_log))
            self.echo_end()
            return False

        self.echo_info("文件压缩完成，耗时{:.2f}秒，压缩包大小：{}".format(time.time() - stime,
                                                          public.to_size(
                                                              tar_size)))
        self.echo_info("目录已备份到：{}".format(filename))

        # 上传文件
        self.echo_info("正在上传到{}，请稍候...".format(self._title))
        if self.upload_file(filename, data_type=data_type):
            self.echo_info("已成功上传到{}".format(self._title))
        else:
            self.echo_error('错误：文件上传失败，跳过本次备份!')
            if os.path.exists(filename):
                os.remove(filename)
            return False

        # 添加备份记录
        object_name = self.build_object_name(data_type, base_file_name)
        tag = self.CONFIG_SEPARATOR + self._name + \
              self.CONFIG_SEPARATOR + base_file_name
        db_filename = object_name + tag

        endDate = time.strftime('%Y/%m/%d %X', time.localtime())
        outTime = time.time() - startTime
        sql.table('backup').add('type,name,pid,filename,addtime,size', (
            '2', path, '0', db_filename, endDate,
            os.path.getsize(filename)))
        log = u"目录[" + path + "]备份成功,用时[" + str(round(outTime, 2)) + "]秒";
        public.WriteLog(u'计划任务', log)
        self.echo_info(u"★[" + endDate + "] " + log)
        self.echo_info(u"保留最新的[" + count + u"]份备份")
        self.echo_info(u"排除规则: " + exclude_config)

        # 清理本地文件
        if os.path.exists(filename):
            os.remove(filename)

        # 清理多余备份
        backups = sql.table('backup').where(
            'type=? and pid=? and name=? and filename LIKE "%{}%"'.format(
                self._name),
            ('2', 0, path)).field('id,name,filename').select();

        num = len(backups) - int(count)
        if num > 0:
            for backup in backups:
                _base_file_name = backup["name"]
                _local_file_name = os.path.join(backup_path, _base_file_name)
                if os.path.isfile(_local_file_name):
                    os.remove(_local_file_name)
                    self.echo_info("已清理本地备份文件:" + _local_file_name)

                _filename = backup["filename"]
                if _filename.find(self.CONFIG_SEPARATOR) != -1:
                    info = _filename.split(self.CONFIG_SEPARATOR)
                    os_file_name = info[0]
                else:
                    os_file_name = _filename
                self.delete_object(os_file_name)
                sql.table('backup').where('id=?', (backup['id'],)).delete();
                num -= 1;
                self.echo_info(
                    u"已清理{}过期备份文件：".format(self._title) + os_file_name)
                if num < 1: break;

        if os.path.exists(self._err_log):
            os.remove(self._err_log)
        self.echo_end()

    def backupSiteAll(self, save):
        sites = public.M('sites').field('name').select()
        for site in sites:
            self.backupSite(site['name'], save)

    def backupDatabaseAll(self, save):
        databases = public.M('databases').field('name').select()
        for database in databases:
            self.backupDatabase(database['name'], save)

    # 构造排除
    def get_exclude(self, exclude=[]):
        if not exclude:
            tmp_exclude = os.getenv('BT_EXCLUDE')
            if tmp_exclude:
                exclude = tmp_exclude.split(',')
        if not exclude: return ""
        for ex in exclude:
            self._exclude += " --exclude=\"" + ex + "\""
        self._exclude += " "
        return self._exclude

    # 取数据库字符集
    def get_database_character(self, db_name):
        try:
            import panelMysql
            tmp = panelMysql.panelMysql().query(
                "show create database `%s`" % db_name.strip())
            c_type = str(re.findall("SET\s+([\w\d-]+)\s", tmp[0][1])[0])
            c_types = ['utf8', 'utf-8', 'gbk', 'big5', 'utf8mb4']
            if not c_type.lower() in c_types: return 'utf8'
            return c_type
        except:
            return 'utf8'

    def get_object_info(self, object_name):
        """获取文件对象信息"""
        return True

    def get_function_args(self, func):
        import sys
        if sys.version_info[0] == 3:
            import inspect
            return inspect.getfullargspec(func).args
        else:
            return func.__code__.co_varnames

    def execute_by_comandline(self, args):
        """命令行或计划任务调用

        针对panelBackup._VERSION >=1.2命令行调用
        :param args: 脚本参数
        """
        try:
            import panelBackup
            client = self
            cls_args = self.get_function_args(panelBackup.backup.__init__)
            if "cron_info" in cls_args and len(args) == 5:
                cron_name = args[4]
                cron_info = {
                    "echo": cron_name
                }
                backup_tool = panelBackup.backup(cloud_object=client, cron_info=cron_info)
            else:
                backup_tool = panelBackup.backup(cloud_object=client)
            _type = args[1];
            data = None
            if _type == 'site':
                if args[2].lower() == 'all':
                    backup_tool.backup_site_all(save=int(args[3]))
                else:
                    backup_tool.backup_site(args[2], save=int(args[3]))
                exit()
            elif _type == 'database':
                if args[2].lower() == 'all':
                    backup_tool.backup_database_all(int(args[3]))
                else:
                    backup_tool.backup_database(args[2],
                                                save=int(args[3]))
                exit()
            elif _type == 'path':
                cron_name = ""
                if len(args) == 5:
                    cron_name = args[4]
                backup_tool.backup_path(args[2], save=int(args[3]))
                exit()
            elif _type == 'upload':
                data = client.resumable_upload(args[2]);
            elif _type == 'download':
                data = client.generate_download_url(args[2]);
            # elif _type == 'get':
            #     data = client.get_files(args[2]);
            elif _type == 'list':
                path = "/"
                if len(args) == 3:
                    path = args[2]
                data = client.get_list(path);
            elif _type == 'lib':
                data = client.get_lib()
            elif _type == 'delete_file':
                result = client.delete_object(args[2]);
                if result:
                    print("文件{}删除成功。".format(args[2]))
                else:
                    print("文件{}删除失败!".format(args[2]))
            else:
                data = 'ERROR: 参数不正确!';
            if data:
                print()
                print(json.dumps(data))
        except Exception as e:
            print(e)

    def echo_start(self):
        print("=" * 90)
        print("★开始备份[{}]".format(public.format_date()))
        print("=" * 90)

    def echo_end(self):
        print("=" * 90)
        print("☆备份完成[{}]".format(public.format_date()))
        print("=" * 90)
        print("\n")

    def echo_info(self, msg):
        print("|-{}".format(msg))

    def echo_error(self, msg):
        print("=" * 90)
        print("|-错误：{}".format(msg))

    def GetDiskInfo2(self):
        # 取磁盘分区信息
        temp = public.ExecShell("df -T -P|grep '/'|grep -v tmpfs")[0]
        tempInodes = public.ExecShell("df -i -P|grep '/'|grep -v tmpfs")[0]
        temp1 = temp.split('\n')
        tempInodes1 = tempInodes.split('\n')
        diskInfo = []
        n = 0
        cuts = []
        for tmp in temp1:
            n += 1
            try:
                inodes = tempInodes1[n - 1].split()
                disk = re.findall(
                    r"^(.+)\s+([\w\.]+)\s+([\w\.]+)\s+([\w\.]+)\s+([\w\.]+)\s+([\d%]{2,4})\s+(/.{0,50})$",
                    tmp.strip())
                if disk: disk = disk[0]
                if len(disk) < 6: continue
                if disk[2].find('M') != -1: continue
                if disk[2].find('K') != -1: continue
                if len(disk[6].split('/')) > 10: continue
                if disk[6] in cuts: continue
                if disk[6].find('docker') != -1: continue
                if disk[1].strip() in ['tmpfs']: continue
                arr = {}
                arr['filesystem'] = disk[0].strip()
                arr['type'] = disk[1].strip()
                arr['path'] = disk[6]
                tmp1 = [disk[2], disk[3], disk[4], disk[5]]
                arr['size'] = tmp1
                arr['inodes'] = [inodes[1], inodes[2], inodes[3], inodes[4]]
                diskInfo.append(arr)
            except:
                continue
        return diskInfo

    # 取磁盘可用空间
    def get_disk_free(self, dfile):
        diskInfo = self.GetDiskInfo2()
        if not diskInfo: return '', 0, 0
        _root = None
        for d in diskInfo:
            if d['path'] == '/':
                _root = d
                continue
            if re.match("^{}/.+".format(d['path']), dfile):
                return d['path'], float(d['size'][2]) * 1024, int(
                    d['inodes'][2])
        if _root:
            return _root['path'], float(_root['size'][2]) * 1024, int(
                _root['inodes'][2])
        return '', 0, 0

    # map to list
    def map_to_list(self, map_obj):
        try:
            if type(map_obj) != list and type(map_obj) != str: map_obj = list(
                map_obj)
            return map_obj
        except:
            return []


"""
=============oss===================
"""


class OSSClient(OSClient, object):
    _title = "阿里云OSS"
    _name = "alioss"

    DEFAULT_STORAGE_CLASS = "Standard"

    __access_key_id = None
    __access_key_secret = None
    __endpoint = None
    __bucket_name = None
    backup_path = None
    reload = False

    def __init__(self, load_config=True, config_file=None):
        super(OSSClient, self).__init__(
            load_config=load_config,
            config_file=config_file
        )

    def init_config(self, data):
        """初始化配置文件"""

        if not data:
            return

        self.__access_key_id = data.get("access_key").strip()
        self.__access_key_secret = data.get("secret_key").strip()
        _bucket_name = data.get("bucket_name").strip();
        _endpoint = data.get("bucket_domain").strip();
        if _endpoint.find(_bucket_name) != -1:
            _endpoint = _endpoint.replace(_bucket_name + '.', '');
        self.__bucket_name = _bucket_name
        self.__endpoint = _endpoint;

        bp = data.get("backup_path").strip()
        if not verify_dir_name(bp):
            raise RuntimeError("无效的目录名称。")

        if bp != "/":
            bp = self.get_path(bp)
        if bp:
            self.backup_path = bp
        else:
            self.backup_path = self.default_backup_path

    def get_config(self):
        """获取配置参数"""
        default_config = {
            "access_key": '',
            "secret_key": '',
            "bucket_name": '',
            "bucket_domain": '',
            "backup_path": self.default_backup_path
        }

        try:
            path = self.get_config_file()
            bak_config_path = self.get_bak_config_file()
            if not os.path.exists(path):
                old_bak_config_file = self.get_old_bak_config_file()
                if os.path.exists(bak_config_path):
                    path = bak_config_path
                elif os.path.exists(old_bak_config_file):
                    path = old_bak_config_file
                else:
                    return default_config

            conf = public.readFile(path)
            try:
                # 兼容上一个版本配置文件
                _c = json.loads(conf)
                conf = _c
            except:
                pass

            if isinstance(conf, str) and conf.find(self.CONFIG_SEPARATOR) != -1:
                # 兼容旧格式配置文件
                # conf = access_key + '|' + \
                #        secret_key + '|' + \
                #        bucket_name + '|' + \
                #        bucket_domain + '|' + \
                #        backup_path;
                old_conf = conf.split(self.CONFIG_SEPARATOR)
                if len(old_conf) < 5: old_conf.append(self.default_backup_path);
                if not old_conf[4] or not old_conf[4].strip():
                    old_conf[4] = self.default_backup_path;

                data = {
                    "access_key": old_conf[0],
                    "secret_key": old_conf[1],
                    "bucket_name": old_conf[2],
                    "bucket_domain": old_conf[3],
                    "backup_path": old_conf[4],
                }
                conf = data

            if not conf: return default_config
            if "backup_path" not in conf or not conf['backup_path']:
                conf['backup_path'] = self.get_path(self.default_backup_path)

            if not os.path.exists(bak_config_path):
                public.writeFile(bak_config_path, json.dumps(conf))
            return conf
        except Exception:
            return default_config

    def authorize(self):
        return oss2.Auth(
            self.__access_key_id,
            self.__access_key_secret
        )

    def get_bucket(self):
        """获取存储空间"""
        try:
            auth = self.authorize()
            name = self.__bucket_name
            endpoint = self.__endpoint
            if not endpoint or not name:
                raise OsError("请检查阿里OSS配置是否正确。")
            bucket = oss2.Bucket(auth, endpoint, name)
            return bucket
        except OssError:
            raise OsError(
                "无法连接到阿里云OSS服务器，请检查["
                "AccessKeyId/AccessKeySecret/Endpoint]设置是否正确!")
        except OsError:
            raise 
        except Exception as e:
            raise RuntimeError("获取存储空间失败:" + str(e))

    def resumable_upload(self,
                         local_file_name,
                         object_name=None,
                         progress_callback=None,
                         progress_file_name=None,
                         multipart_threshold=1024 * 1024 * 2,
                         part_size=1024 * 1024 * 2,
                         store_dir="/tmp",
                         auto_cancel=True,
                         retries=2,
                         ):
        """断点续传

        :param local_file_name: 本地文件名称
        :param object_name: 指定OS中存储的对象名称
        :param part_size: 指定分片上传的每个分片的大小。如不指定，则自动计算。
        :param multipart_threshold: 文件长度大于该值时，则用分片上传。
        :param progress_callback: 进度回调函数，默认是把进度信息输出到标准输出。
        :param progress_file_name: 进度信息保存文件，进度格式参见[report_progress]
        :param store_dir: 上传分片存储目录, 默认/tmp。
        :param auto_cancel: 当备份失败是否自动取消上传记录
        :param retries: 上传重试次数
        :return: True上传成功/False or None上传失败
        """

        try:
            bucket = self.get_bucket()
            _error_msg = self.error_msg
            if object_name is None:
                temp_file_name = os.path.split(local_file_name)[1]
                object_name = self.backup_path + temp_file_name

            oss2.defaults.connection_pool_size = 4;
            num_threads = oss2.defaults.multipart_num_threads

            if progress_file_name:
                os.environ[PROGRESS_FILE_NAME] = progress_file_name
                progress_callback = report_progress
            # elif progress_callback is None:
            #     progress_callback = percentage

            if object_name[:1] == "/":
                object_name = object_name[1:]

            print("|-正在上传到 {}...".format(object_name))
            result = oss2.resumable_upload(
                bucket,
                object_name,
                local_file_name,
                store=oss2.ResumableStore(root=store_dir),
                part_size=part_size,
                multipart_threshold=multipart_threshold,
                num_threads=num_threads,
                progress_callback=progress_callback,
            )
            if result.status == 200 or result.status == 204:
                return True
            if self.error_msg:
                self.error_msg += r"\n"
            self.error_msg += "文件{}上传失败：错误信息:{}/{}".format(
                object_name, result.status, result.resp)
            print("resp:")
            print(result.resp)
        except OsError as e:
            raise OsError(str(e))
        except Exception as e:
            print("文件上传出现错误：")
            print(e)
            if self.error_msg:
                self.error_msg += r"\n"
            self.error_msg += "文件{}上传出现错误：{}".format(object_name, str(e))


        # 重试断点续传
        if retries > 0:
            print("重试上传文件....")
            return self.resumable_upload(
                local_file_name,
                object_name=object_name,
                store_dir=store_dir,
                part_size=part_size,
                multipart_threshold=multipart_threshold,
                progress_callback=progress_callback,
                progress_file_name=progress_file_name,
                retries=retries - 1,
            )
        else:
            if auto_cancel:
                # 取消断点续传
                self.cancel_upload(object_name)
        if self.error_msg:
            self.error_msg += r"\n"
        self.error_msg += "文件{}上传失败。".format(object_name)
        return False

    def get_list(self, path="/", delimiter="/"):
        """获取存储空间中的所有文件对象"""

        bucket = self.get_bucket()
        data = []
        path = self.get_path(path);

        from itertools import islice
        for b in islice(
                oss2.ObjectIterator(bucket,
                                    prefix=path,
                                    delimiter=delimiter),
                1000):
            b.key = b.key.replace(path, '');
            if not b.key: continue;
            tmp = {}
            tmp['name'] = b.key
            tmp['size'] = b.size
            tmp['type'] = b.type
            tmp['download'] = self.generate_download_url(path + b.key);
            tmp['time'] = b.last_modified
            data.append(tmp)

        mlist = {'path': path, 'list': data}
        return mlist

    def create_dir(self, dir_name):
        """创建远程目录

        :param dir_name: 目录名称
        :return:
        """

        dir_name = dir_name.strip()
        if not verify_dir_name(dir_name):
            raise RuntimeError("无效目录名称。")

        dir_name = self.get_path(dir_name)
        if dir_name[:1] == "/":
            dir_name = dir_name[1:]

        file_name = '/tmp/dirname.pl';
        public.writeFile(file_name, '');
        bucket = self.get_bucket()
        result = bucket.put_object_from_file(dir_name, file_name)
        if result.status == 200:
            return True
        os.remove(file_name);

    def cancel_upload(self, object_name):
        """取消断点续传

        意义: 上传的文件如果按照时间生成，每次传入的文件名都不一样。如果某个文件在断点续传中途
        中断，这个文件可能永远都不会被再次启动续传。而这些已上传的文件分片会一直占用OS的存储空间。
        :param object_name:
        :return:
        """

        print("取消文件{}上传...".format(object_name))
        try:
            bucket = self.get_bucket()
            upload_id = None
            # 查找本次上传的upload id
            from itertools import islice
            # print("已有分片上传文件:")
            for multi_upload in oss2.MultipartUploadIterator(
                    bucket):
                # print(multi_upload.key)
                if object_name == multi_upload.key:
                    print("upload_id:" + multi_upload.upload_id)
                    upload_id = multi_upload.upload_id
                    break
            print("upload_id:" + repr(upload_id))
            # 取消断点续传
            result = bucket.abort_multipart_upload(object_name,
                                                   upload_id)
            if result.status == 200 or result.status == 204:
                # TODO 删除本地进度文件
                print("取消文件{}上传成功。".format(object_name))
                return True
            else:
                print("取消文件{}上传失败。"
                      "已上传文件分片会占用多余的存储空间，请及时清理。".format(object_name))
        except Exception as e:
            print(e)
            print("取消文件{}上传失败。"
                  "已上传文件分片会占用多余的存储空间，请及时清理。".format(object_name))

    def download_file(self,
                      object_name,
                      file_name,
                      progress_file_name=None,
                      progress_callback=None,
                      multiget_threshold=1024 * 1024 * 2,
                      part_size=1024 * 1024 * 2,
                      store_dir="/tmp",
                      retries=2):
        """文件下载

        :param object_name: OS中存储的对象名称
        :param file_name: 存储到本地的文件名称
        :param part_size: 分片下载的每个分片的大小。如不指定，则自动计算。
        :param multiget_threshold: 文件长度大于该值时，则用分片下载。
        :param progress_callback: 进度回调函数，默认是把进度信息输出到标准输出。
        :param progress_file_name: 进度信息保存文件，进度格式参见[report_progress]
        :param store_dir: 下载分片存储目录
        :param retries: 下载重试次数
        :return: True下载成功/False or None下载失败
        :raises NoSuchKey: 对象不存在错误。
                OsError: 与OS平台相关的错误
                RuntimeError: 出现其他未知错误，触发重试机制之后抛出。
        """
        try:
            import time
            start_time = time.time()
            bucket = self.get_bucket()
            num_threads = oss2.defaults.multiget_num_threads

            if object_name[:1] == "/":
                object_name = object_name[1:]

            if os.path.isdir(os.path.abspath(file_name)):
                temp_file_name = os.path.split(object_name)[-1]
                file_name += temp_file_name

            if progress_file_name:
                os.environ[PROGRESS_FILE_NAME] = progress_file_name
                progress_callback = report_progress
            # elif progress_callback is None:
            #     progress_callback = percentage

            # 断点续传下载
            print("开始下载文件{}".format(object_name))
            oss2.resumable_download(
                bucket,
                object_name,
                file_name,
                store=oss2.ResumableDownloadStore(root=store_dir),
                multiget_threshold=multiget_threshold,
                part_size=part_size,
                num_threads=num_threads,
                progress_callback=progress_callback,
            )

            # 验证
            print()
            print("验证文件...")
            if not os.path.isfile(file_name):
                print("文件下载失败。")
            else:
                crc64 = self.calculate_file_crc64(file_name,
                                                  block_size=part_size)
                result = bucket.head_object(object_name)
                if str(crc64) == result.headers['x-oss-hash-crc64ecma']:
                    print("文件下载完成。")
                    return True
                else:
                    print("文件验证失败。")
        except (NoSuchKey, NotFound) as e:
            print("下载目标文件{}不存在。".format(object_name))
            raise ObjectNotFound("下载目标文件{}不存在。".format(object_name))
        except OssError as e:
            raise OsError(str(e))
        except Exception as e:
            import time
            now = time.time()
            print("下载文件{}出现错误[{}]:".format(object_name, now) + str(e))

        if retries > 0:
            return self.download_file(object_name,
                                      file_name,
                                      progress_file_name=progress_file_name,
                                      progress_callback=progress_callback,
                                      multiget_threshold=multiget_threshold,
                                      part_size=part_size,
                                      store_dir=store_dir,
                                      retries=retries - 1)
        return False

    def generate_download_url(self, object_name, expires=60 * 60):
        """生成下载url

        :param object_name: 对象名称
        :param expires: 过期时间（单位：秒），默认1小时。
        :return: 签名URL。
        """
        try:
            request_method = "GET"
            bucket = self.get_bucket()
            ori_url = bucket.sign_url(
                request_method,
                object_name,
                expires,
                # slash_safe=True
            )
            standard_url = ori_url.replace("%2F", "/")
            return standard_url
        except Exception as e:
            raise RuntimeError("生成下载链接出现错误:" + str(e))

    def delete_object_by_os(self, object_name):
        """删除对象

        注意：OSS SDK不论object name是否存在，删除请求状态都返回204。
        如果你的对象不在os的存储空间当中，删除操作也会返回True。
        :param object_name:
        :param retries: 重试次数，默认2次
        :return: True 删除成功
                其他 删除失败
        """

        bucket = self.get_bucket()
        result = bucket.delete_object(object_name)
        if result.status == 200 or result.status == 204:
            return True

    def batch_delete(self, object_names):
        """批量删除对象

        :param object_names:
        :type object_names: list
        :return:
        """
        try:
            bucket = self.get_bucket()
            result = bucket.batch_delete_objects(object_names)
            if result.status == 200 or result.status == 204:
                return True
        except Exception as e:
            raise RuntimeError("批量删除文件出现错误:" + str(e))

    def calculate_file_crc64(self, file_name, block_size=64 * 1024, init_crc=0):
        """计算文件的MD5
        :param file_name: 文件名
        :param block_size: 计算MD5的数据块大小，默认64KB
        :return 文件内容的MD5值
        """
        with open(file_name, 'rb') as f:
            crc64 = oss2.utils.Crc64(init_crc)
            while True:
                data = f.read(block_size)
                if not data:
                    break
                crc64.update(data)

        return crc64.crc


"""
=============插件主文件Main===================
"""


class alioss_main(object):
    __client = None
    __error_count = 0
    __error_msg = "ERROR: 无法连接到阿里云OSS服务器，请检查[" \
                  "AccessKeyId/AccessKeySecret/Endpoint]设置是否正确!"

    def __init__(self):
        try:
            self.get_lib()
        except:
            pass

    @property
    def client(self):
        if self.__client:
            return self.__client;
        self.__client = OSSClient()
        return self.__client

    def get_config(self, get):
        return self.client.get_config()

    def set_config(self, get):
        try:
            access_key = get.access_key.strip()
            secret_key = get.secret_key.strip()
            bucket_name = get.bucket_name.strip()
            bucket_domain = get.bucket_domain.strip()
            backup_path = get.backup_path.strip()
            # 验证前端输入
            values = [access_key,
                      secret_key,
                      bucket_name,
                      bucket_domain]
            for v in values:
                if not v:
                    return public.returnMsg(False, '必填资料不能为空，请核实!');

            if not backup_path:
                backup_path = "bt_backup"

            data = {
                "access_key": access_key,
                "secret_key": secret_key,
                "bucket_name": bucket_name,
                "bucket_domain": bucket_domain,
                "backup_path": backup_path,
            }
            _client = OSSClient(load_config=False)
            _client.init_config(data)
            if _client.get_list():
                _client.set_config(data)
                return public.returnMsg(True, '设置成功!');
        except oss2.exceptions.ServerError as e:
            try:
                info = e
                if hasattr(e, "details"):
                    if "Code" in e.details:
                        msg_code = e.details["Code"]
                        if msg_code == "RequestTimeTooSkewed":
                            return public.returnMsg(False, "请尝试同步本地时间后再尝试，本地时间与OSS服务器时间不一致。")
                        else:
                            return public.returnMsg(False, e.details["Message"]);
            except Exception as e2:
                pass

        return public.returnMsg(False, 'API资料校验失败，请核实!');

    # 创建目录
    def create_dir(self, get):
        try:
            path = get.path + "/" + get.dirname;
            if self.client.create_dir(path):
                return public.returnMsg(True, '创建成功!');
            else:
                return public.returnMsg(False, "创建失败！")
        except Exception as e:
            return public.returnMsg(False, "目录创建失败:" + str(e))

    # 获取列表
    def get_list(self, get):
        try:
            return self.client.get_list(get.path)
        except:
            return public.returnMsg(False, "获取列表失败！")

    # 删除文件
    def delete_file(self, get):
        try:
            path = get.path
            filename = get.filename
            if path[-1] != "/":
                file_name = path + "/" + filename
            else:
                file_name = path + filename

            if file_name[-1] == "/":
                return public.returnMsg(False, "暂时不支持目录删除！")

            if file_name[:1] == "/":
                file_name = file_name[1:]
            if self.client.delete_object(file_name):
                return public.returnMsg(True, '删除成功')
            return public.returnMsg(False, '文件{}删除失败！'.format(file_name))
        except:
            return public.returnMsg(False, '文件删除失败!')

    # 下载文件
    def download_file(self, filename):
        """生成下载文件链接

        从文件名反推出文件在云存储中的真实下载链接
        下载链接根据当前的存储路径拼接，如果存储路径发生过改变，链接会失效。
        :filename: 备份文件名
            格式参考：web_192.168.1.245_20200703_183016.tar.gz
        """
        import re
        _result = re.search("([^_]+)_.+", filename)
        if _result:
            file_type = _result.group(1)
            reversal_prefix_dict = {
                "web": "site",
                "db": "database",
                "path": "path",
            }
            data_type = reversal_prefix_dict.get(file_type)
            object_name = self.client.build_object_name(data_type,
                                                        filename)
            return self.client.generate_download_url(object_name)
        else:
            return filename

    def get_lib(self):
        import json
        info = {
            "name": self.client._title,
            "type": "计划任务",
            "ps": "将网站或数据库打包备份到阿里云OSS对象存储空间,阿里云OSS提供5GB免费存储空间, "
                  "<a class='link' "
                  "href='https://www.aliyun.com/product/oss?spm=5176.8142029"
                  ".388261.46.psCRgl' target='_blank'>点击申请</a>",
            "status": 'false',
            "opt": "alioss",
            "module": "alioss",
            "script": "alioss",
            "help": "http://www.bt.cn/bbs/thread-1061-1-1.html",
            "AccessKeyID": "AccessKeyID|请输入AccessKeyID|阿里云的AccessKeyId",
            "SecretKey": "SecretKey|请输入SecretKey|阿里云的AccessKeySecret ",
            "Bucket": "存储空间名称|阿里云OSS中您创建的Bucket名称",
            "Domain": "阿里云OSS外链域名，不包括Bucket名",
            "backup_path": "备份保存路径, 默认是/bt_backup",
            "check": [
                "/usr/lib/python2.7/site-packages/oss2/__init__.py",
                "/www/server/panel/pyenv/bin/python3.7/site-packages/oss2"
                "/__init__.py"
            ]
        }
        lib = '/www/server/panel/data/libList.conf'
        lib_dic = json.loads(public.readFile(lib))
        for i in lib_dic:
            if info['name'] in i['name']:
                return True
            else:
                pass
        lib_dic.append(info)
        public.writeFile(lib, json.dumps(lib_dic))
        return lib_dic


if __name__ == "__main__":
    import json
    import panelBackup

    data = None

    new_version = True if hasattr(panelBackup, "_VERSION") \
            and panelBackup._VERSION >= 1.2 else False
    client = OSSClient();
    if not new_version:
        _type = sys.argv[1];
        if _type == 'site':
            if sys.argv[2].lower() == "all":
                client.backupSiteAll(sys.argv[3])
            else:
                client.backupSite(sys.argv[2], sys.argv[3])
            exit()
        elif _type == 'database':
            if sys.argv[2].lower() == "all":
                client.backupDatabaseAll(sys.argv[3])
            else:
                client.backupDatabase(sys.argv[2], sys.argv[3])
            exit()
        elif _type == 'path':
            client.backupPath(sys.argv[2], sys.argv[3])
        elif _type == 'upload':
            data = client.upload_file(sys.argv[2]);
        elif _type == 'download':
            data = client.generate_download_url(sys.argv[2]);
        elif _type == 'get':
            data = client.get_object_info(sys.argv[2]);
        elif _type == 'list':
            path = "/"
            if len(sys.argv) == 3:
                path = sys.argv[2]
            data = client.get_list(path);
        elif _type == 'delete_file':
            data = client.delete_file(sys.argv[2]);
        else:
            data = 'ERROR: 参数不正确!';
        if data:
            print(json.dumps(data))
    else:
        client.execute_by_comandline(sys.argv)
