import requests
from bs4 import BeautifulSoup
import pandas as pd
from Course_class import Course
# from Course_class import Departments
import os

PRE = 1
CO = 1
EXC = 0

# URL of the course list page
URL = "https://w5.ab.ust.hk/wcq/cgi-bin/"

def removeSpace(string):
    ret = []
    for char in string:
        if char != " " and char != "(" and char != ")":
            ret.append(char)
    return ''.join(ret)

def isNumber(string):
    try:
        i = int(string)
        return True
    except Exception as e:
        return False

def fetch_course_data(time,department):
    url = URL+str(time)+'/'+"subject/"+department
    # Send a GET request to the page
    response = requests.get(url)
    response.raise_for_status()  # Ensure the request was successful
    # print(response)
    # Parse the page using BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')
    # print(soup)
    # print(soup.body)
    
    # Find all course blocks
    classes = soup.body.find('div', attrs={'id': 'classes'})
    # print(classes)
    courses = classes.find_all('div', attrs={'class': 'course'})
    # print(courses)
    departmentData = []
    for course in courses:
        # Extract course code and title
        # print(data)
        c = Course()
        code_ = course.find('div', class_='subject').get_text(strip=True)
        # _code = course.find('div', class_='courseanchor').get_text(strip=True)
        # __code = _code.split('\"')
        # print(course.courseanchor)
        # print(_code)
        # print(__code)
        # code = __code[1]

        # title = course.find('div', class_='course-title').get_text(strip=True)
        code_and_title = code_.split(" - ")
        if(len(code_and_title)>=2):
            code = removeSpace(code_and_title[0])
            title = ''.join(code_and_title[1:-1])+code_and_title[-1][:-9]
            if code_and_title[-1][-2] == 's':
                credit = int(code_and_title[-1][-8])
            else:
                credit = int(code_and_title[-1][-7])
        else:
            code = code_
            title = "unknown"
            credit = -1
        
        # Extract description, pre-requisite, and co-requisite if available
        details = course.find('div', attrs={'class': 'courseattr'}).find_all('tr')
        description = ""
        prerequisite = ""
        corequisite = ""
        exclusion = ""
        for detail in details:
            if detail.find('th') == None:
                continue
            if detail.find('th').get_text(strip=True) == 'DESCRIPTION':
                description = detail.find('td').get_text(strip=True)
            if detail.find('th').get_text(strip=True) == 'PRE-REQUISITE':
                prerequisite = detail.find('td').get_text(strip=True)
            if detail.find('th').get_text(strip=True) == 'CO-REQUISITE':
                corequisite = detail.find('td').get_text(strip=True)
            if detail.find('th').get_text(strip=True) == 'EXCLUSION':
                exclusion = detail.find('td').get_text(strip=True)

        if description == "": 
            description =  'N/A'
        if prerequisite == "":
            prerequisite = 'N/A'
        if corequisite == "":
            corequisite = 'N/A'
        if exclusion == "":
            exclusion = 'N/A'

        pre_course = []
        for i in range(len(prerequisite)):
            if (prerequisite[i:i+4] in Departments) and (isNumber(prerequisite[i+5:i+8])):
                pre_course.append(" [["+removeSpace(prerequisite[i:i+10])+"]] ")
            if prerequisite[i:i+2] == "OR":
                pre_course.append("or")
            if prerequisite[i:i+3] == "AND":
                pre_course.append("and")
            if prerequisite[i] == '(' or prerequisite[i] == ')':
                pre_course.append(prerequisite[i])
        
        co_course = []
        for i in range(len(corequisite)):
            if (corequisite[i:i+4] in Departments) and (isNumber(corequisite[i+5:i+8])):
                co_course.append(" [["+removeSpace(corequisite[i:i+10])+"]] ")
            if corequisite[i:i+2] == "OR":
                co_course.append("or")
            if corequisite[i:i+3] == "AND":
                co_course.append("and")
            if corequisite[i] == '(' or corequisite[i] == ')':
                co_course.append(corequisite[i])
        
        exc_course = []
        for i in range(len(exclusion)):
            if (exclusion[i:i+4] in Departments) and (isNumber(exclusion[i+5:i+8])):
                exc_course.append(" [["+removeSpace(exclusion[i:i+10])+"]] ")
            if exclusion[i:i+2] == "OR":
                exc_course.append("or")
            if exclusion[i:i+3] == "AND":
                exc_course.append("and")
            if exclusion[i] == '(' or exclusion[i] == ')':
                exc_course.append(exclusion[i])

        # Append the details to the data list
        c.changeAttribute(code,title,description,prerequisite,corequisite,exclusion,credit)
        c.changeRelated(pre_course,co_course,exc_course)
        departmentData.append(c)
        # print(len(departmentData))
    # print(data)
    return departmentData

def save_to_excel(data, filename='courses.xlsx'):
    # Create a pandas DataFrame and save to Excel
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    print(f"Data saved to {filename}")

def create_md(department,data):
    os.makedirs("Courses/"+department,exist_ok=True)
    for course in data:
        filename = "Courses/"+department+"/"+course.code+".md"
        course_file = open(filename,"w")
        course_file.write("# Description\n")
        course_file.write(course.title+"\n")
        course_file.write(course.description+"\n")
        course_file.write("#cre: "+str(course.cre)+"\n\n")
        course_file.write("# Pre:\n")
        course_file.write(course.pre+"\n")
        for pre_ in course.pre_c:
            if type(pre_) == str:
                if PRE:
                    course_file.write(pre_)
            else:
                course_file.write("[["+pre_.code+"]]\n")
        course_file.write("\n")
        course_file.write("# Co:\n")
        course_file.write(course.co+"\n")
        for co_ in course.co_c:
            if type(co_) == str:
                if CO:
                    course_file.write(co_)
            else:
                course_file.write("[["+co_.code+"]]\n")
        course_file.write("\n")
        course_file.write("# Exc:\n")
        course_file.write(course.exc+"\n")
        for exc_ in course.exc_c:
            if type(exc_) == str:
                if EXC:
                    course_file.write(exc_)
            else:
                course_file.write("[["+exc_.code+"]]\n")
        course_file.write("\n")
        course_file.close()

def get_dept(time):
    response = requests.get(URL+str(time)+'/')
    response.raise_for_status()  # Ensure the request was successful
    print(response)
    # Parse the page using BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')
    allDepartments = soup.body.find('div', class_ = 'depts').find('div', attrs={'id' : 'subjectItems'})
    departs = allDepartments.find_all('a')
    departments = []
    for depart in departs:
        departments.append(depart.get_text(strip = True))
    # print(departments)
    return departments


if __name__ == "__main__":
    try:
        print("Fetching course data...")
        for i in range(1,5):
            Departments = get_dept(2400+10*i)
            print(Departments)
            # exit()
            for dept in Departments:
                course_data = fetch_course_data(2400+10*i,dept)

                print(f"Found {len(course_data)} courses in {dept} in {i}th semester. Saving to Md...",end='')
                create_md(dept,course_data)
                print("Done")
        print("Done!")

    except Exception as e:
        print(f"An error occurred: {e}")