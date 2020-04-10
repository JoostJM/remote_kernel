import tkinter


class PwdDialog(tkinter.Tk):

  def __init__(self, title, prompt=None):
    super(PwdDialog, self).__init__()
    self.title(title)
    self.geometry("400x80")
    self.frame = tkinter.Frame()
    self.pwd = tkinter.StringVar()
    if prompt is None:
      prompt = 'password?'
    self.lblPrompt = tkinter.Label(self, text=prompt).pack()
    self.txtPwd = tkinter.Entry(self, show="*", textvariable=self.pwd).pack()
    self.btnOK = tkinter.Button(self, text='Ok', command=self.btnOK_click).pack()
    self.OK = False

  def btnOK_click(self):
    self.OK = True
    self.destroy()

  def showDialog(self):
    self.mainloop()
    assert self.OK, 'Dialog cancelled by user'
    return self.pwd.get()

class PromptDialog(tkinter.Tk):

  def __init__(self, title, prompt):
    super(PromptDialog, self).__init__()
    self.title(title)
    self.geometry("400x80")
    self.frame = tkinter.Frame()
    self.pwd = tkinter.StringVar()
    self.lblPrompt = tkinter.Label(self.frame, text=prompt).pack()
    self.txtPwd = tkinter.Entry(self.frame,textvariable=self.pwd).pack()
    self.btnOK = tkinter.Button(self.frame, text='Ok', command=self.btnOK_click).pack()

  def btnOK_click(self):
    self.destroy()

  def showDialog(self):
    self.mainloop()
    assert self.OK, 'Dialog cancelled by user'
    return self.pwd.get()
