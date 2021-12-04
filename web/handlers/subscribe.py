#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# vim: set et sw=4 ts=4 sts=4 ff=unix fenc=utf8:
# Author: Binux<i@binux.me>
#         http://binux.me
# Created on 2014-08-08 21:06:02

import json
import os
import traceback
import time
import base64
import random
from tornado import gen
from .base import *
from config import proxies 
from libs.fetcher import Fetcher
from libs.utils import find_encoding
from urllib.parse import quote
fetcher = Fetcher()

class SubscribeHandler(BaseHandler):
    @tornado.web.addslash
    @tornado.web.authenticated
    async def get(self, userid):
        msg = ''
        user = self.current_user
        adminflg = False
        if (user['id'] == int(userid)) and (user['role'] == u'admin'):
            adminflg = True
        repos = json.loads(self.db.site.get(1, fields=('repos'))['repos'])
        try:
            if proxies:
                proxy = random.choice(proxies)
            else:
                proxy = {}
            now_ts = int(time.time())
            # 如果上次更新时间大于1天则更新模板仓库
            if (now_ts - int(repos['lastupdate']) > 24 * 3600):
                tpls = self.db.pubtpl.list()
                await self.render('pubtpl_wait.html', tpls=tpls, user=user, userid=user['id'], adminflg=adminflg, repos=repos['repos'], msg=msg)
                return

            tpls = self.db.pubtpl.list()
            await self.render('pubtpl_subscribe.html', tpls=tpls, user=user, userid=user['id'], adminflg=adminflg, repos=repos['repos'], msg=msg)

        except Exception as e:
            traceback.print_exc()
            user = self.current_user
            tpls = self.db.pubtpl.list()
            await self.render('pubtpl_subscribe.html', tpls=tpls, user=user, userid=user['id'], adminflg=adminflg, repos=repos['repos'], msg=str(e))
            return

class SubscribeUpdatingHandler(BaseHandler):
    @tornado.web.addslash
    @tornado.web.authenticated
    async def get(self, userid):
        msg = ''
        user = self.current_user
        adminflg = False
        if (user['id'] == int(userid)) and (user['role'] == u'admin'):
            adminflg = True
        repos = json.loads(self.db.site.get(1, fields=('repos'))['repos'])
        try:
            if proxies:
                proxy = random.choice(proxies)
            else:
                proxy = {}
            now_ts = int(time.time())
            # 如果上次更新时间大于1天则更新模板仓库
            if (now_ts - int(repos['lastupdate']) > 24 * 3600):
                for repo in repos['repos']:
                    if repo['repoacc']:
                        url = '{0}@{1}'.format(repo['repourl'].replace('https://github.com/', 'https://cdn.jsdelivr.net/gh/'), repo['repobranch'])
                    else:
                        if (repo['repourl'].find('https://github.com/') > -1):
                            url = '{0}/{1}'.format(repo['repourl'].replace('https://github.com/', 'https://raw.githubusercontent.com/'), repo['repobranch'])
                        else:
                            url = repo['repourl']

                    hfile_link = url + '/tpls_history.json'
                    obj = {'request': {'method': 'GET', 'url': hfile_link, 'headers': [], 'cookies': []}, 'rule': {
                        'success_asserts': [], 'failed_asserts': [], 'extract_variables': []}, 'env': {'variables': {}, 'session': []}}
                    _,_,res = await gen.convert_yielded(fetcher.build_response(obj = obj, proxy = proxy))
                    if res.code == 200:
                        hfile = json.loads(res.body.decode(find_encoding(res.body, res.headers), 'replace'))
                        for har in hfile['har'].values():
                            if (har['content'] == ''):
                                obj['request']['url'] = "{0}/{1}".format(url, quote(har['filename']))
                                _,_,har_res = await gen.convert_yielded(fetcher.build_response(obj, proxy = proxy))
                                if har_res.code == 200:
                                    har['content'] = base64.b64encode(har_res.body).decode()
                                else:
                                    msg += '{pre}\r\n打开链接错误{link}\r\n'.format(pre=msg, link=obj['request']['url'])
                                    continue

                            for k, v in repo.items():
                                har[k] = v
                            tpl = self.db.pubtpl.list(name = har['name'], 
                                                      reponame=har['reponame'],
                                                      repourl=har['repourl'], 
                                                      repobranch=har['repobranch'], 
                                                      fields=('id', 'name', 'version'))

                            if (len(tpl) > 0):
                                if (int(tpl[0]['version']) < int(har['version'])):
                                    har['update'] = True
                                    self.db.pubtpl.mod(tpl[0]['id'], **har)
                            else:
                                self.db.pubtpl.add(har)
                    else:
                        msg += '{pre}\r\n打开链接错误{link}\r\n'.format(pre=msg, link=obj['request']['url'])
            repos["lastupdate"] = now_ts
            self.db.site.mod(1, repos=json.dumps(repos, ensure_ascii=False, indent=4))
            
            if msg:
                raise Exception(msg)

            tpls = self.db.pubtpl.list()

            await self.render('pubtpl_subscribe.html', tpls=tpls, user=user, userid=user['id'], adminflg=adminflg, repos=repos['repos'], msg=msg)
            return

        except Exception as e:
            traceback.print_exc()
            user = self.current_user
            tpls = self.db.pubtpl.list()
            await self.render('pubtpl_subscribe.html', tpls=tpls, user=user, userid=user['id'], adminflg=adminflg, repos=repos['repos'], msg=str(e))
            return

class SubscribeRefreshHandler(BaseHandler):
    @tornado.web.authenticated
    async def post(self, userid):
        try:
            user = self.current_user
            op = self.get_argument('op', '')
            if (op == ''):
                raise Exception('op参数为空')

            if (user['id'] == int(userid)) and (user['role'] == u'admin'):
                repos = json.loads(self.db.site.get(1, fields=('repos'))['repos'])
                repos["lastupdate"] = 0
                self.db.site.mod(1, repos=json.dumps(repos, ensure_ascii=False, indent=4))
                if (op == 'clear'):
                    for pubtpl in self.db.pubtpl.list(fields=('id')):
                        self.db.pubtpl.delete(pubtpl['id'])
            else:
                raise Exception('没有权限操作')
        except Exception as e:
            traceback.print_exc()
            await self.render('utils_run_result.html', log=str(e), title=u'设置失败', flg='danger')
            return

        self.redirect('/subscribe/{0}/'.format(userid) ) 
        return

class Subscrib_signup_repos_Handler(BaseHandler):
    @tornado.web.authenticated
    async def get(self, userid):
        user = self.current_user
        if (user['id'] == int(userid)) and (user['role'] == u'admin'):
            await self.render('pubtpl_register.html', userid=userid)
        else:
            await self.render('utils_run_result.html', log='非管理员用户，不可设置', title=u'设置失败', flg='danger')
        return

    @tornado.web.authenticated
    async def post(self, userid):
        try:
            user = self.current_user
            if (user['id'] == int(userid)) and (user['role'] == u'admin'):
                envs = {}
                for key in self.request.body_arguments:
                    envs[key] = self.get_body_arguments(key)
                env = {}
                for k, v  in envs.items():
                    if (v[0] == 'false') or (v[0] == 'true'):
                        env[k] = True if v[0] == 'true' else False
                    else:
                        env[k] = v[0]

                if (env['reponame'] != '') and (env['repourl'] != '') and (env['repobranch'] != ''):
                    repos = json.loads(self.db.site.get(1, fields=('repos'))['repos'])
                    tmp = repos['repos']
                    inflg = False

                    # 检查是否存在同名仓库
                    for repo in repos['repos']:
                        if repo['reponame'] == env['reponame']:
                            inflg = True
                            break

                    if inflg:
                        raise Exception('已存在同名仓库')
                    else:
                        tmp.append(env)
                        repos['repos'] = tmp
                        repos["lastupdate"] = 0
                        self.db.site.mod(1, repos=json.dumps(repos, ensure_ascii=False, indent=4))
                else:
                    raise Exception('仓库名/url/分支不能为空')
            else:
                raise Exception('非管理员用户，不可设置')

        except Exception as e:
            traceback.print_exc()
            await self.render('utils_run_result.html', log=str(e), title=u'设置失败', flg='danger')
            return

        await self.render('utils_run_result.html', log=u'设置成功，请关闭操作对话框或刷新页面查看', title=u'设置成功', flg='success')
        return

class GetReposInfoHandler(BaseHandler):
    @tornado.web.authenticated
    async def post(self, userid):
        try:
            user = self.current_user
            if (user['id'] == int(userid)) and (user['role'] == u'admin'):
                envs = {}
                for key in self.request.body_arguments:
                    envs[key] = self.get_body_arguments(key)
                tmp = json.loads(self.db.site.get(1, fields=('repos'))['repos'])['repos']
                repos = []
                for repoid, selected  in envs.items():
                    if isinstance(selected[0],bytes):
                        selected[0] = selected[0].decode()
                    if (selected[0] == 'true'):
                        repos.append(tmp[int(repoid)])
            else:
                raise Exception('非管理员用户，不可查看')
        except Exception as e:
            traceback.print_exc()
            await self.render('utils_run_result.html', log=str(e), title=u'获取信息失败', flg='danger')
            return

        await self.render('pubtpl_reposinfo.html',  repos=repos)
        return

class unsubscribe_repos_Handler(BaseHandler):
    @tornado.web.authenticated
    async def get(self, userid):
        try:
            user = self.current_user
            if (user['id'] == int(userid)) and (user['role'] == u'admin'):
                await self.render('pubtpl_unsubscribe.html', user=user)
            else:
                raise Exception('非管理员用户，不可设置')
            return
        except Exception as e:
            traceback.print_exc()
            await self.render('utils_run_result.html', log=str(e), title=u'打开失败', flg='danger')
            return
    
    @tornado.web.authenticated
    async def post(self, userid):
        try:
            user = self.current_user
            if (user['id'] == int(userid)) and (user['role'] == u'admin'):
                envs = {}
                for key in self.request.body_arguments:
                    envs[key] = self.get_body_arguments(key)
                env = {}
                for k, v  in envs.items():
                    try:
                        env[k] = json.loads(v[0])
                    except:
                        env[k] = v[0]
                repos = json.loads(self.db.site.get(1, fields=('repos'))['repos'])
                tmp = repos['repos']
                result = []
                for i, j  in enumerate(tmp):
                    # 检查是否存在同名仓库
                    if not env['selectedrepos'].get(str(i),False) :
                        result.append(j)
                    else:
                        pubtpls = self.db.pubtpl.list(reponame=j['reponame'], fields=('id'))
                        for pubtpl in pubtpls:
                            self.db.pubtpl.delete(pubtpl['id'])
                repos['repos'] = result
                self.db.site.mod(1, repos=json.dumps(repos, ensure_ascii=False, indent=4))
            else:
                raise Exception('非管理员用户，不可设置')

        except Exception as e:
            traceback.print_exc()
            await self.render('utils_run_result.html', log=str(e), title=u'设置失败', flg='danger')
            return

        await self.render('utils_run_result.html', log=u'设置成功，请关闭操作对话框或刷新页面查看', title=u'设置成功', flg='success')
        return

handlers = [
        ('/subscribe/(\d+)/', SubscribeHandler),
        ('/subscribe/(\d+)/updating/', SubscribeUpdatingHandler),
        ('/subscribe/refresh/(\d+)/', SubscribeRefreshHandler),
        ('/subscribe/signup_repos/(\d+)/', Subscrib_signup_repos_Handler),
        ('/subscribe/(\d+)/get_reposinfo', GetReposInfoHandler),
        ('/subscribe/unsubscribe_repos/(\d+)/', unsubscribe_repos_Handler),
        ]

