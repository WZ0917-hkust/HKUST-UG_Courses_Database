class Course:
    def changeAttribute(self,code_,title_,description_,pre_,co_,exc_,cre_):
        self.code = code_
        self.title = title_
        self.description = description_
        self.pre = pre_
        self.co  = co_
        self.exc = exc_
        self.cre = cre_
        return
    
    def changeRelated(self,pre_c_,co_c_,exc_c_):
        for pre_c in pre_c_:
            self.pre_c.append(pre_c)
        for co_c in co_c_:
            self.co_c.append(co_c)
        for exc_c in exc_c_:
            self.exc_c.append(exc_c)
        return
    
    def __init__(self):
        self.code = "N/A"
        self.title = "N/A"
        self.description = "N/A"
        self.pre = "N/A"
        self.pre_c = []
        self.co = "N/A"
        self.co_c = []
        self.exc = "N/A" #exclusion
        self.exc_c = []
        self.cre = 0
'''
    def __init__(self,code_,title_,description_,pre_,co_,exc_,cre_):
        self.__init__()
        self.changeAttribute(code_,title_,description_,pre_,co_,exc_,cre_)

    def __init__(self,code_,title_,description_,pre_,co_,exc_,cre_,pre_c_ = None,co_c_ = None,exc_c_ = None):
        self.__init__()
        self.changeAttribute(code_,title_,description_,pre_,co_,exc_,cre_)
        self.changeRelated(pre_c_,co_c_,exc_c_)
        '''

Departments = ["ACCT","AESF","AIAA","AISC","AMAT","BEHI","BIBU","BIEN","BSBE","BTEC","CENG","CHEM","CHMS","CIEM","CIVL","CMAA","COMP","CPEG","CSIC","CSIT","CTDL","DASC","DBAP","DRAP","DSAA","DSCT","ECON","EEMT","EESM","ELEC","EMIA","ENEG","ENGG","ENTR","ENVR","ENVS","EOAS","EVNG","EVSM","FINA","FTEC","GBUS","GNED","HLTH","HMAW","HMMA","HUMA","IBTM","IEDA","IIMP","INTR","IOTA","IPEN","ISDN","ISOM","JEVE","LABU","LANG","LIFS","MAED","MAFS","MARK","MASS","MATH","MCEE","MECH","MESF","MFIT","MGCS","MGMT","MICS","MILE","MIMT","MSBD","MSDM","MTLE","NANO","OCES","PDEV","PHYS","PPOL","RMBI","ROAS","SBMT","SCIE","SEEN","SHSS","SMMG","SOSC","SUST","TEMG","UCOP","UGOD","UPOP","UROP","UTOP","WBBA"]

'''  
class Department:
    def __init__(self):
        self.courses = {}
    
    def add_course(self,course_):
        self.courses[course_.code] = course_

    def del_course(self,course_): # this function will be useless
        del self.courses[course_.code]

    def create_course(self,code_,title_,description_,pre_,co_,exc_)
'''