### PROMPTS -----------
# -----------------------------------------
Prompt_Used_For_One_Employee = """
Lets create a transcript of a zoom meeting with detailed minute by minute conversation of 
30 minuteswhich is in between two indivisuals one is manager Saurabh Mishra and the second is Devesh Mishra
 the employee who is reporting to Saurabh Mishra. Both are working in the AI Team. Meeting is about 30 mins 
 long and the discussion starts with some comprehensive development in the current project which was assigned to 
 Devesh Mishra 1week before now both talk on some challenges and previous usecases of some related projects and in the 
 last 5 minutes Devesh Mishra closes by explaining the effort and execution in moving feature to production and Saurabh 
 Praises Devesh with some Rcognition and then Devesh mentions some other employees name from other teams to his manager 
 about how they helped in completing this project then again Saurabh recgnises and appriceates each one of these employees
   performance. Also the generated transcript should start on 11 AM and should end at 11:30  AM which means the conversation 
   is a bit descriptive with some more information added in the mean-time.
"""
Prompt_Used_For_Multiple_Employee = """
Create a detailed, minute-by-minute transcript of a 30-minute Zoom meeting, scheduled from 11:00 AM to 11:30 AM.
The meeting is between a manager, Saurabh Mishra, and the key members of a project team. The attendees are Devesh Mishra from the AI team, along with Shivam and Manish from the Fullstack team. All are reporting on the progress of a project assigned one week ago.
The discussion should start with a comprehensive development update. Devesh should first detail the progress on the core AI model. Afterwards, Shivam and Manish should provide a summary of their work on the fullstack components, such as API integration and the user interface.
Following the updates, the conversation should shift to the challenges they encountered. Devesh should discuss AI-specific problems and how he leveraged previous use cases and related projects for solutions. Shivam and Manish should then talk about the challenges they faced on the fullstack side.
In the last five minutes, the team should collaboratively explain the effort and execution plan for moving the entire feature to production.
After their summary, Saurabh Mishra should praise and recognize the excellent work and teamwork of Devesh, Shivam, and Manish. To conclude the meeting, one of the team members should mention the names of other employees from different teams (e.g., Data Platform, SRE) who were helpful in completing the project. Saurabh should then also recognize and appreciate the performance and collaborative spirit of each of these individuals.
The entire transcript should be descriptive, with detailed technical and project-related information added throughout to realistically fill the 30-minute timeframe.
"""
# -----------------------------------------