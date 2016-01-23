import os, os.path
import random
import string
import cherrypy
import mysql.connector
import subprocess
import tinys3
import boto
import boto.s3
import sys
from cherrypy.lib import sessions
from boto.s3.key import Key
from jinja2 import Environment, FileSystemLoader

# declare global variables
env = Environment(loader=FileSystemLoader('staticFiles/templates'))
S3_ACCESS_KEY = 'AKIAI2L42BGVQS5V57QA'
S3_SECRET_KEY = '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'
signedIn = False
config = {
        'user': 'Floptical',
        'password': 'Password1',
        'host': 'floptical-relational-database.cxrbiaxhps5f.us-west-2.rds.amazonaws.com',
        'database': 'flopticalDatabase'
}

adminEmail = 'admin@floptical.com'

class ServeSite(object):
	@cherrypy.expose
	def home(self):
		if(cherrypy.session.get('loggedIn', 'None') == False):
			return "You need to sign in"
		cnx = mysql.connector.connect(**config)
		cursor = cnx.cursor()
		args = ()
		cursor.callproc('sp_get_all_videos',args)
		videos = """<div class="row">"""
		for result in cursor.stored_results():
			for row in result:
				videos = videos + """<div class="col-md-4">"""
				videos = videos + """<h2>%s</h2>"""%row[1]
				videos = videos + """<video width="350" height="200" controls>
										<source src="%s" type="video/mp4">
										Your browser does not support HTML5 video
									</video></div>"""%row[2]
		#		videos = videos + """</div>"""
		cnx.close()
		tmpl = env.get_template('home.html')
		return tmpl.render()%videos

	@cherrypy.expose
	def index(self, signin=''):
		cherrypy.session['loggedIn'] = False
		tmpl = env.get_template('index.html')
		return tmpl.render()%signin

	@cherrypy.expose
	def admin(self, uploadMessage=''):
		if(cherrypy.session.get('admin', 'None') == True):
			cnx = mysql.connector.connect(**config)
			cursor = cnx.cursor()
			args = ()
			cursor.callproc('sp_get_all_videos',args)
			videoTable = """"""
			for result in cursor.stored_results():
				for row in result:
					videoTable = videoTable + """<tr>"""
					videoTable = videoTable + """<td>%s</td>"""%row[1]
					videoTable = videoTable + """<td>%s</td>"""%row[3]
					videoTable = videoTable + """<td>%s</td>"""%row[4]
					videoTable = videoTable + """<td>%s</td>"""%row[5]
					# going to put username here
					videoTable = videoTable +"""<td></td>"""
					videoTable = videoTable + """<td><form enctype="multipart/form-data" action="deleteFiles" method="post">
													<input type="submit" name="deleteVideo" value="Delete Video">
													<input type=hidden value="%s"name="videoIdToDelete">
											</form></td>"""%row[0]
					videoTable = videoTable + """</tr>"""
			cnx.close()
			tmpl = env.get_template('admin.html')
			return tmpl.render()%(uploadMessage,videoTable)
		else:
			raise cherrypy.HTTPRedirect("/home")

	@cherrypy.expose
        def createUser(self, cu_fName, cu_lName, cu_sex, cu_email, cu_password):
                cnx = mysql.connector.connect(**config)
                cursor = cnx.cursor()
		ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
		chars=[]
		for i in range(16):
			chars.append(random.choice(ALPHABET))
		salt = "".join(chars)
		args = (cu_email, cu_password, salt, cu_fName, cu_lName, cu_sex, cu_email, "", "", "", "")
                cursor.callproc("sp_register_user", args)
		cnx.commit()
		cnx.close()
                return self.index()

	@cherrypy.expose
        def signin(self, signin_email, signin_password):
                cnx = mysql.connector.connect(**config)
                cursor = cnx.cursor()
                args = (signin_email, signin_password, 0 )
		result1 = cursor.callproc("sp_check_password", args)
                out = result1[2]
		if(out == 1):
			if(signin_email == adminEmail):
				cherrypy.session['admin'] = True

                        cherrypy.session['loggedIn'] = True
                        raise cherrypy.HTTPRedirect("/home")
                else:
                        cherrypy.session['loggedIn'] = False
                        raise cherrypy.HTTPRedirect("/index?signin='Incorrect credentials'")
		cnx.close()
	@cherrypy.expose
	def saveFiles(self, uploadFile, vName, vQuality, username):
		if(uploadFile.file is None):
			return """Must provide a file"""
		else:
			basename = os.path.basename(uploadFile.filename)
			fn = 'uploadedFiles/' + basename
			vDuration = 'unspecified'
			f = open(fn,'wb').write(uploadFile.file.read())
			bucket_name = 'floptical'

			# get vDuration
			result = subprocess.Popen(["ffprobe", fn],
				stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
			for x in result.stdout.readlines():
				if "Duration" in x:
					vDuration = x
			vDuration = str(vDuration[12:20])

			# connect to the s3 bucket
			conn = boto.connect_s3(S3_ACCESS_KEY,S3_SECRET_KEY)
			bucket = conn.get_bucket(bucket_name,validate=False)

			# create a key to keep track of file in storage
			key = 'videos/' + basename
			k = Key(bucket)
			k.key = key
			k.set_contents_from_filename(fn)
			# retrieve url from s3
			public_url = k.generate_url(0,query_auth=False,force_http=True)

			# delete file from server
			os.remove(fn)

			# establish connection to database
			cnx = mysql.connector.connect(**config)
			cursor = cnx.cursor()
			args = (vName, public_url,vDuration,vQuality, '')
			# query mysql databse to add video meta-data
			dataOut = str(cursor.callproc('sp_add_video',args))
			# commit change to database
			cnx.commit()
			# close connection to database
			cnx.close()
			raise cherrypy.HTTPRedirect("/admin?uploadMessage='Upload Successful!'")

	@cherrypy.expose
	def deleteFiles(self, deleteVideo, videoIdToDelete):
		cnx = mysql.connector.connect(**config)
		cursor = cnx.cursor()
		args = [videoIdToDelete]
	#	conn = boto.connect_s3(S3_ACCESS_KEY, S3_SECRET_KEY)
	#	bucket = conn.get_bucket('floptical')
	#	videoName = cursor.callproc('sp_get_video_name_by_id',[videoIdToDelete,''])[1]
	#	key = 'videos/' + videoName
	#	bucket.delete_key(key)
		cursor.callproc('sp_delete_video_by_id',args)
		cnx.commit()
		cnx.close()
		raise cherrypy.HTTPRedirect("/admin")



if __name__ == '__main__':
	conf = {
		'global': {
		'server.max_request_body_size': 0
		},
		'/': {
			'tools.sessions.on' : True,
			'tools.staticdir.root' : os.path.abspath(os.getcwd())
		},
		'/static': {
			'tools.staticdir.on': True,
			'tools.staticdir.dir': './staticFiles'
		}
	}

cherrypy.server.socket_host = '0.0.0.0'
cherrypy.quickstart(ServeSite(), '/',conf)


