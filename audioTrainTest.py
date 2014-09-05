import sys, numpy, time, os, glob, mlpy, cPickle, shutil, audioop, signal
import scipy.io.wavfile as wavfile
from matplotlib.mlab import find
import matplotlib.pyplot as plt
import scipy.io as sIO
from scipy import linalg as la
import audioFeatureExtraction as aF
from scipy.spatial import distance

def signal_handler(signal, frame):
        print 'You pressed Ctrl+C! - EXIT'
	os.system("stty -cbreak echo")
        sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

shortTermWindow = 0.020
shortTermStep = 0.020
eps = 0.00000001


class kNN:
	def __init__(self, X, Y, k):
		self.X = X
		self.Y = Y
		self.k = k
	def classify(self, testSample):
		nClasses = numpy.unique(self.Y).shape[0]
		YDist =  (distance.cdist(self.X, testSample.reshape(1, testSample.shape[0]), 'euclidean')).T
		iSort = numpy.argsort(YDist)
		P = numpy.zeros((nClasses,))
		for i in range(nClasses):
			P[i] = numpy.nonzero(self.Y[iSort[0][0:self.k]]==i)[0].shape[0] / float(self.k)
		return (numpy.argmax(P), P)

def classifierWrapper(classifier, classifierType, testSample):
	'''
	This function is used as a wrapper to pattern classification.
	ARGUMENTS:
		- classifier:		a classifier object of type mlpy.LibSvm or kNN (defined in this library)
		- classifierType:	"svm" or "knn"
		- testSample:		a feature vector (numpy array)
	RETURNS:
		- R:			class ID
		- P:			probability estimate

	EXAMPLE (for some audio signal stored in array x):
		import audioFeatureExtraction as aF
		import audioTrainTest as aT
		# load the classifier (here SVM, for kNN use loadKNNModel instead):
		[Classifier, MEAN, STD, classNames, mtWin, mtStep, stWin, stStep] = aT.loadSVModel(modelName)
		# mid-term feature extraction:
		[MidTermFeatures, _] = aF.mtFeatureExtraction(x, Fs, mtWin * Fs, mtStep * Fs, round(Fs*stWin), round(Fs*stStep));
		# feature normalization:
		curFV = (MidTermFeatures[:, i] - MEAN) / STD;
		# classification
		[Result, P] = classifierWrapper(Classifier, modelType, curFV)		
	'''
	R = -1; P = -1
	if classifierType == "knn":
		[R, P] = classifier.classify(testSample)
	elif classifierType == "svm":		
		R = classifier.pred(testSample)
		P = classifier.pred_probability(testSample)
	return [R, P]

def randSplitFeatures(features, partTrain):
	"""
	def randSplitFeatures(features):
	
	This function splits a feature set for training and testing.
	
	ARGUMENTS:
		- features: 		a list ([numOfClasses x 1]) whose elements containt numpy matrices of features.
					each matrix features[i] of class i is [numOfSamples x numOfDimensions] 
		- partTrain:		percentage 
	RETURNS:
		- featuresTrains:	a list of training data for each class
		- featuresTest:		a list of testing data for each class
	"""

	featuresTrain = []
	featuresTest = []
	for i,f in enumerate(features):
		[numOfSamples, numOfDims] = f.shape
		randperm = numpy.random.permutation(range(numOfSamples))
		nTrainSamples = int(round(partTrain * numOfSamples));
		featuresTrain.append(f[randperm[1:nTrainSamples]])
		featuresTest.append(f[randperm[nTrainSamples+1:-1]])
	return (featuresTrain, featuresTest)

def trainKNN(features, K):
	'''
	Train a kNN  classifier.
	Note: 	This function is simply a wrapper to the mlpy-knn classifier
		See function trainKNN_feature() to use a wrapper on both the feature extraction and the SVM training (and parameter tuning) processes.
	ARGUMENTS:
		- features: 		a list ([numOfClasses x 1]) whose elements containt numpy matrices of features.
					each matrix features[i] of class i is [numOfSamples x numOfDimensions] 
		- K:			parameter K 
	RETURNS:
		- kNN:			the trained kNN variable

	'''
	[Xt, Yt] = listOfFeatures2Matrix(features)
	knn = kNN(Xt, Yt, K)
	return knn

def trainSVM(features, Cparam):
	'''
	Train a multi-class probabilitistic SVM classifier.
	Note: 	This function is simply a wrapper to the mlpy-LibSVM functionality for SVM training
		See function trainSVM_feature() to use a wrapper on both the feature extraction and the SVM training (and parameter tuning) processes.
	ARGUMENTS:
		- features: 		a list ([numOfClasses x 1]) whose elements containt numpy matrices of features.
					each matrix features[i] of class i is [numOfSamples x numOfDimensions] 
		- Cparam:		SVM parameter C (cost of constraints violation)
	RETURNS:
		- svm:			the trained SVM variable

	NOTE:	
		This function trains a linear-kernel SVM for a given C value. For a different kernel, other types of parameters should be provided.
		For example, gamma for a polynomial, rbf or sigmoid kernel. Furthermore, Nu should be provided for a nu_SVM classifier.
		See MLPY documentation for more details (http://mlpy.sourceforge.net/docs/3.4/svm.html)
	'''
	[X, Y] = listOfFeatures2Matrix(features)	
	svm = mlpy.LibSvm(svm_type='c_svc', kernel_type='linear', eps=0.0000001, C = Cparam, probability=True)
	svm.learn(X, Y)	
	return svm

def featureAndTrain(listOfDirs, mtWin, mtStep, stWin, stStep, classifierType, modelName):
	'''
	This function is used as a wrapper to segment-based audio feature extraction and classifier training.
	ARGUMENTS:
		listOfDirs:		list of paths of directories. Each directory contains a signle audio class whose samples are stored in seperate WAV files.
		mtWin, mtStep:		mid-term window length and step
		stWin, stStep:		short-term window and step
		classifierType:		"svm" or "knn"
		modelName:		name of the model to be saved
	RETURNS: 
		None. Resulting classifier along with the respective model parameters are saved on files.
	'''
	# STEP A: Feature Extraction:
	[features, classNames, _] = aF.dirsWavFeatureExtraction(listOfDirs, mtWin, mtStep, stWin, stStep)

	if len(features)==0:
		print "trainSVM_feature ERROR: No data found in any input folder!"
		return
	for i,f in enumerate(features):
		if len(f)==0:
			print "trainSVM_feature ERROR: " + listOfDirs[i] + " folder is empty or non-existing!"
			return

	# STEP B: Classifier Evaluation and Parameter Selection:
	if classifierType == "svm":
		classifierParams = numpy.array([0.001, 0.01,  0.5, 1.0, 5.0, 10.0])
	elif classifierType == "knn":
		classifierParams = numpy.array([1, 3, 5, 7, 9, 11, 13, 15]); 

	# get optimal classifeir parameter:
	bestParam = evaluateClassifier(features, classNames, 100, classifierType, classifierParams, 0)

	print "Selected params: {0:.5f}".format(bestParam)

	C = len(classNames)
	[featuresNorm, MEAN, STD] = normalizeFeatures(features)		# normalize features
	MEAN = MEAN.tolist(); STD = STD.tolist()
	featuresNew = featuresNorm 
	
	# STEP C: Save the classifier to file
	if classifierType == "svm":
		Classifier = trainSVM(featuresNew, bestParam)
		Classifier.save_model(modelName)
		fo = open(modelName + "MEANS", "wb")
		cPickle.dump(MEAN, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(STD,  fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(classNames,  fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(mtWin, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(mtStep, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(stWin, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(stStep, fo, protocol = cPickle.HIGHEST_PROTOCOL)
	    	fo.close()
	elif classifierType == "knn":
		[X, Y] = listOfFeatures2Matrix(featuresNew)
		X = X.tolist(); Y = Y.tolist()
		fo = open(modelName, "wb")
		cPickle.dump(X, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(Y,  fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(MEAN, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(STD,  fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(classNames,  fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(bestParam,  fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(mtWin, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(mtStep, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(stWin, fo, protocol = cPickle.HIGHEST_PROTOCOL)
		cPickle.dump(stStep, fo, protocol = cPickle.HIGHEST_PROTOCOL)
	    	fo.close()

def loadKNNModel(kNNModelName):
	try:
		fo = open(kNNModelName, "rb")
	except IOError:
       		print "didn't find file"
        	return
    	try:
		X     = cPickle.load(fo)
		Y     = cPickle.load(fo)
		MEAN  = cPickle.load(fo)
		STD   = cPickle.load(fo)
		classNames =  cPickle.load(fo)
		K     = cPickle.load(fo)
		mtWin = cPickle.load(fo)
		mtStep = cPickle.load(fo)
		stWin = cPickle.load(fo)
		stStep = cPickle.load(fo)
    	except:
        	fo.close()
	fo.close()	

	X = numpy.array(X)
	Y = numpy.array(Y)
	MEAN = numpy.array(MEAN)
	STD = numpy.array(STD)

	Classifier = kNN(X, Y, K) # Note: a direct call to the kNN constructor is used here, since the 

	return(Classifier, MEAN, STD, classNames, mtWin, mtStep, stWin, stStep);

def loadSVModel(SVMmodelName):
	try:
		fo = open(SVMmodelName+"MEANS", "rb")
	except IOError:
       		print "Load SVM Model: Didn't find file"
        	return
    	try:
		MEAN     = cPickle.load(fo)
		STD      = cPickle.load(fo)
		classNames =  cPickle.load(fo)
		mtWin = cPickle.load(fo)
		mtStep = cPickle.load(fo)
		stWin = cPickle.load(fo)
		stStep = cPickle.load(fo)
    	except:
        	fo.close()
	fo.close()	

	MEAN = numpy.array(MEAN)
	STD  = numpy.array(STD)

	COEFF = []
	SVM = mlpy.LibSvm.load_model(SVMmodelName)

	return(SVM, MEAN, STD, classNames, mtWin, mtStep, stWin, stStep);				

def evaluateClassifier(features, ClassNames, nExp, ClassifierName, Params, parameterMode):
	'''
	ARGUMENTS:
		features: 	a list ([numOfClasses x 1]) whose elements containt numpy matrices of features.
				each matrix features[i] of class i is [numOfSamples x numOfDimensions] 
		ClassNames:	list of class names (strings)
		Gammas:		list of possible Gamma parameters in the SVM Model
		Nus:		list of possible Nus parameters in the SVM model
		ClassifierName:	"svm" or "knn"
		parameterMode:	0: choose parameters that lead to maximum overall classification ACCURACY
				1: choose parameters that lead to maximum overall F1 MEASURE
	RETURNS:
	 	bestParam:	the value of the input parameter that optimizes the selected performance measure		
	'''

	# feature normalization:
	(featuresNorm, MEAN, STD) = normalizeFeatures(features)

	nClasses = len(features)
	CAll = []; acAll = []; F1All = []	
	PrecisionClassesAll = []; RecallClassesAll = []; ClassesAll = []; F1ClassesAll = []
	CMsAll = []

	for Ci, C in enumerate(Params):				# for each Nu value		

				CM = numpy.zeros((nClasses, nClasses))
				for e in range(nExp):		# for each cross-validation iteration:
					# split features:
					featuresTrain, featuresTest = randSplitFeatures(featuresNorm, 0.50)
					# train multi-class svms:
					if ClassifierName=="svm":
						Classifier = trainSVM(featuresTrain, C)
					elif ClassifierName=="knn":
						Classifier = trainKNN(featuresTrain, C)

					CMt = numpy.zeros((nClasses, nClasses))
					for c1 in range(nClasses):
						#Results = Classifier.pred(featuresTest[c1])
						nTestSamples = len(featuresTest[c1])
						Results = numpy.zeros((nTestSamples,1))
						for ss in range(nTestSamples):
							[Results[ss], _] = classifierWrapper(Classifier, ClassifierName, featuresTest[c1][ss])
						for c2 in range(nClasses):
							CMt[c1][c2] = float(len(numpy.nonzero(Results==c2)[0]))
					CM = CM + CMt
				CM = CM + 0.0000000010
				Rec = numpy.zeros((CM.shape[0],))
				Pre = numpy.zeros((CM.shape[0],))

				for ci in range(CM.shape[0]):
					Rec[ci] = CM[ci,ci] / numpy.sum(CM[ci,:]);
					Pre[ci] = CM[ci,ci] / numpy.sum(CM[:,ci]);
				PrecisionClassesAll.append(Pre)
				RecallClassesAll.append(Rec)
				F1 = 2 * Rec * Pre / (Rec + Pre)
				F1ClassesAll.append(F1)
				acAll.append(numpy.sum(numpy.diagonal(CM)) / numpy.sum(CM))

				CMsAll.append(CM)
				F1All.append(numpy.mean(F1))
				# print "{0:6.4f}{1:6.4f}{2:6.1f}{3:6.1f}".format(nu, g, 100.0*acAll[-1], 100.0*F1All[-1])

	print ("\t\t"),
	for i,c in enumerate(ClassNames): 
		if i==len(ClassNames)-1: print "{0:s}\t\t".format(c),  
		else: print "{0:s}\t\t\t".format(c), 
	print ("OVERALL")
	print ("\tC"),
	for c in ClassNames: print "\tPRE\tREC\tF1", 
	print "\t{0:s}\t{1:s}".format("ACC","F1")
	bestAcInd = numpy.argmax(acAll)
	bestF1Ind = numpy.argmax(F1All)
	for i in range(len(PrecisionClassesAll)):
		print "\t{0:.3f}".format(Params[i]),
		for c in range(len(PrecisionClassesAll[i])):
			print "\t{0:.1f}\t{1:.1f}\t{2:.1f}".format(100.0*PrecisionClassesAll[i][c], 100.0*RecallClassesAll[i][c], 100.0*F1ClassesAll[i][c]), 
		print "\t{0:.1f}\t{1:.1f}".format(100.0*acAll[i], 100.0*F1All[i]),
		if i == bestF1Ind: print "\t best F1", 
		if i == bestAcInd: print "\t best Acc",
 		print

	if parameterMode==0:	# keep parameters that maximize overall classification accuracy:
		print "Confusion Matrix:"
		printConfusionMatrix(CMsAll[bestAcInd], ClassNames)
		return Params[bestAcInd]
	elif parameterMode==1:  # keep parameters that maximize overall F1 measure:
		print "Confusion Matrix:"
		printConfusionMatrix(CMsAll[bestF1Ind], ClassNames)
		return Params[bestF1Ind]

def printConfusionMatrix(CM, ClassNames):
	'''
	This function prints a confusion matrix for a particular classification task.
	ARGUMENTS:
		CM:		a 2-D numpy array of the confusion matrix 
				(CM[i,j] is the number of times a sample from class i was classified in class j)
		ClassNames:	a list that contains the names of the classes
	'''

	if CM.shape[0] != len(ClassNames):
		print "printConfusionMatrix: Wrong argument sizes\n"
		return

	for c in ClassNames: 
		if len(c)>4: 
			c = c[0:3]
		print "\t{0:s}".format(c),
	print

	for i, c in enumerate(ClassNames):
		if len(c)>4: c = c[0:3]
		print "{0:s}".format(c),
		for j in range(len(ClassNames)):
			print "\t{0:.1f}".format(100.0*CM[i][j] / numpy.sum(CM)),
		print

def normalizeFeatures(features):
	'''
	This function nromalizes a feature set to 0-mean and 1-std.
	Used in most classifier trainning cases.

	ARGUMENTS:
		- features:	list of feature matrices (each one of them is a numpy matrix)
	RETURNS:
		- featuresNorm:	list of NORMALIZED feature matrices
		- MEAN:		mean vector
		- STD:		std vector
	'''
	X = numpy.array([])
	
	for count,f in enumerate(features):
		if f.shape[0]>0:
			if count==0:
				X = f
			else:
				X = numpy.vstack((X, f))
			count += 1
	
	MEAN = numpy.mean(X, axis = 0)
	STD  = numpy.std( X, axis = 0)

	featuresNorm = []
	for f in features:
		ft = f.copy()
		for nSamples in range(f.shape[0]):
			ft[nSamples,:] = (ft[nSamples,:] - MEAN) / STD	
		featuresNorm.append(ft)
	return (featuresNorm, MEAN, STD)

def listOfFeatures2Matrix(features):
	'''
	listOfFeatures2Matrix(features)
	
	This function takes a list of feature matrices as argument and returns a single concatenated feature matrix and the respective class labels.

	ARGUMENTS:
		- features:		a list of feature matrices

	RETURNS:
		- X:			a concatenated matrix of features
		- Y:			a vector of class indeces	
	'''

	X = numpy.array([])
	Y = numpy.array([])
	for i,f in enumerate(features):
		if i==0:
			X = f
			Y = i * numpy.ones((len(f), 1))
		else:
			X = numpy.vstack((X, f))
			Y = numpy.append(Y, i * numpy.ones((len(f), 1)))
	return (X, Y)

def listOfFeatures2MatrixRegression(features, Ys):
	'''
	listOfFeatures2MatrixRegression(features)
	
	Same as MatrixRegression but used for regression (also takes real values as arguments)

	ARGUMENTS:
		- features:		a list of feature matrices
		- Ys:			a list of respective real values

	RETURNS:
		- X:			a concatenated matrix of features
		- Y:			a vector of class indeces	
	'''

	X = numpy.array([])
	Y = numpy.array([])
	for i,f in enumerate(features):
		if i==0:
			X = f
			Y = Ys[i] * numpy.ones((len(f), 1))
		else:
			X = numpy.vstack((X, f))
			Y = numpy.append(Y, Ys[i] * numpy.ones((len(f), 1)))
	return (X, Y)
	

def pcaDimRed(features, nDims):
	[X, Y] = listOfFeatures2Matrix(features)
	pca = mlpy.PCA(method='cov')
	pca.learn(X)
	coeff = pca.coeff()
	coeff = coeff[:,0:nDims]

	featuresNew = []
	for f in features:
		ft = f.copy()
#		ft = pca.transform(ft, k=nDims)
		ft = numpy.dot(f, coeff)
		featuresNew.append(ft)

	return (featuresNew, coeff)

def fileClassification(inputFile, modelName, modelType):
	# Load classifier:

	if not os.path.isfile(modelName):
		print "fileClassification: input modelName not found!"
		return (-1,-1, -1)

	if not os.path.isfile(inputFile):
		print "fileClassification: input modelType not found!"
		return (-1,-1, -1)


	if modelType=='svm':
		[Classifier, MEAN, STD, classNames, mtWin, mtStep, stWin, stStep] = loadSVModel(modelName)
	elif modelType=='knn':
		[Classifier, MEAN, STD, classNames, mtWin, mtStep, stWin, stStep] = loadKNNModel(modelName)
			
	[Fs, x] = aF.readAudioFile(inputFile)		# read audio file and convert to mono
	x = aF.stereo2mono(x);
	# feature extraction:
	[MidTermFeatures, s] = aF.mtFeatureExtraction(x, Fs, mtWin * Fs, mtStep * Fs, round(Fs*stWin), round(Fs*stStep));
	MidTermFeatures = MidTermFeatures.mean(axis=1)		# long term averaging of mid-term statistics
	curFV = (MidTermFeatures - MEAN) / STD;			# normalization
	[Result, P] = classifierWrapper(Classifier, modelType, curFV)	# classification
	return Result, P, classNames


def lda(data,labels,redDim):

    # Centre data
    data -= data.mean(axis=0)
    nData = numpy.shape(data)[0]
    nDim = numpy.shape(data)[1]
    print nData, nDim
    Sw = numpy.zeros((nDim,nDim))
    Sb = numpy.zeros((nDim,nDim))
    
    C = numpy.cov((data.T))

    # Loop over classes    
    classes = numpy.unique(labels)
    for i in range(len(classes)):
        # Find relevant datapoints
        indices = (numpy.where(labels==classes[i]))
        d = numpy.squeeze(data[indices,:])
        classcov = numpy.cov((d.T))
        Sw += float(numpy.shape(indices)[0])/nData * classcov
        
    Sb = C - Sw
    # Now solve for W
    # Compute eigenvalues, eigenvectors and sort into order
    #evals,evecs = linalg.eig(dot(linalg.pinv(Sw),sqrt(Sb)))
    evals,evecs = la.eig(Sw,Sb)
    indices = numpy.argsort(evals)
    indices = indices[::-1]
    evecs = evecs[:,indices]
    evals = evals[indices]
    w = evecs[:,:redDim]
    #print evals, w


    newData = numpy.dot(data,w)
    #for i in range(newData.shape[0]):
    #	plt.text(newData[i,0],newData[i,1],str(labels[i]))

    #plt.xlim([newData[:,0].min(), newData[:,0].max()])
    #plt.ylim([newData[:,1].min(), newData[:,1].max()])
    #plt.show()
    return newData,w


def main(argv):


	if argv[1]=='-c': # CALIBRATION:
		if len(argv)>6:
			
			numOfBlocks = float(argv[2])
			midTermBufferSizeSec = float(argv[3])
			calibrationFileName = argv[4]
			calibrationPath = argv[5]
			modelName = argv[6]
			otherClasses = argv[7:len(argv)]
			print otherClasses
			if os.path.isfile(modelName):

				os.system("stty cbreak -echo")
				print "A model already exists with the same file name. Are you sure you want to continue (the existing model will be replaced) (y/n):",
				ANS = sys.stdin.read(1)
				os.system("stty -cbreak echo")

				if ANS.lower()=='y':
					os.remove(modelName)
					if os.path.isfile(modelName+"MEANS"):
						os.remove(modelName + "MEANS")
				else:
					return

			calibrationClasses, dirNames = calibrationTraining2(numOfBlocks, midTermBufferSizeSec, calibrationFileName, calibrationPath)
			dirNames = dirNames + otherClasses
			trainSVM_feature(dirNames, midTermBufferSizeSec, midTermBufferSizeSec, shortTermWindow, shortTermStep, modelName)

	
if __name__ == '__main__':
	main(sys.argv)
